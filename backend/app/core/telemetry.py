from __future__ import annotations

import copy
import importlib.util
import logging
import os
import sys
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI, Request, Response

from app.core.config import Settings

logger = logging.getLogger(__name__)

_PROXY_ENV_VARS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
_TELEMETRY_STATUS: dict[str, Any] = {
    "configured": False,
    "enabled": False,
    "status": "not_configured",
    "reason": "APPLICATIONINSIGHTS_CONNECTION_STRING is empty.",
    "dependencies": {},
    "connection": {},
    "proxy": {},
    "live_metrics_enabled": False,
}


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def _dependency_status() -> dict[str, bool]:
    return {
        "azure.monitor.opentelemetry": _module_available("azure.monitor.opentelemetry"),
        "opentelemetry.instrumentation.fastapi": _module_available("opentelemetry.instrumentation.fastapi"),
        "opentelemetry.sdk.resources": _module_available("opentelemetry.sdk.resources"),
    }


def _suffix(value: str | None, chars: int = 6) -> str | None:
    if not value:
        return None
    return value[-chars:]


def _parse_connection_string(connection_string: str | None) -> dict[str, str | None]:
    if not connection_string:
        return {}

    parts: dict[str, str] = {}
    for segment in connection_string.split(";"):
        if "=" not in segment:
            continue
        key, value = segment.split("=", 1)
        parts[key.strip().lower()] = value.strip().rstrip("/")

    return {
        "ingestion_endpoint": parts.get("ingestionendpoint"),
        "live_endpoint": parts.get("liveendpoint"),
        "instrumentation_key_suffix": _suffix(parts.get("instrumentationkey")),
        "application_id_suffix": _suffix(parts.get("applicationid")),
    }


def _sanitize_proxy_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.hostname:
        return "<configured>"

    host = parsed.hostname
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, "", "", ""))


def _proxy_status() -> dict[str, Any]:
    targets = {
        name: _sanitize_proxy_url(value)
        for name in _PROXY_ENV_VARS
        if (value := os.environ.get(name))
    }
    return {
        "configured": bool(targets),
        "variables": sorted({name.upper() for name in targets}),
        "targets": targets,
        "no_proxy_configured": bool(os.environ.get("NO_PROXY") or os.environ.get("no_proxy")),
    }


def _set_telemetry_status(**updates: Any) -> None:
    global _TELEMETRY_STATUS
    _TELEMETRY_STATUS = {
        **_TELEMETRY_STATUS,
        **updates,
        "proxy": _proxy_status(),
    }


def get_telemetry_status() -> dict[str, Any]:
    status = copy.deepcopy(_TELEMETRY_STATUS)
    status["proxy"] = _proxy_status()
    return status


def configure_telemetry(app: FastAPI, settings: Settings) -> None:
    connection_string = settings.applicationinsights_connection_string
    dependencies = _dependency_status()
    base_status = {
        "configured": bool(connection_string),
        "enabled": False,
        "dependencies": dependencies,
        "connection": _parse_connection_string(connection_string),
        "live_metrics_enabled": settings.applicationinsights_live_metrics_enabled,
    }
    app.state.azure_monitor_enabled = False

    if "pytest" in sys.modules:
        _set_telemetry_status(
            **base_status,
            status="disabled_pytest",
            reason="Application Insights telemetry is disabled during pytest.",
        )
        logger.info("Application Insights telemetry is disabled during pytest.")
        return

    if not connection_string:
        _set_telemetry_status(
            **base_status,
            status="not_configured",
            reason="APPLICATIONINSIGHTS_CONNECTION_STRING is empty.",
        )
        logger.info("Application Insights telemetry is disabled: no connection string configured.")
        return

    missing_dependencies = [name for name, available in dependencies.items() if not available]
    if missing_dependencies:
        reason = f"Missing telemetry dependencies: {', '.join(missing_dependencies)}"
        _set_telemetry_status(**base_status, status="dependency_missing", reason=reason)
        logger.warning("Application Insights telemetry is configured but dependencies are missing: %s", ", ".join(missing_dependencies))
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except ImportError as exc:
        _set_telemetry_status(**base_status, status="dependency_missing", reason=str(exc))
        logger.warning("Application Insights telemetry is configured but dependencies are missing: %s", exc)
        return

    try:
        configure_azure_monitor(
            connection_string=connection_string,
            enable_live_metrics=settings.applicationinsights_live_metrics_enabled,
            logger_name="app",
            resource=Resource.create(
                {
                    "service.name": "cloudapp-backend",
                    "service.namespace": "cloudapp",
                    "deployment.environment": settings.environment,
                }
            ),
        )
        FastAPIInstrumentor.instrument_app(app)
        app.state.azure_monitor_enabled = True
        _set_telemetry_status(**base_status, enabled=True, status="enabled", reason=None)
        logger.info("Application Insights telemetry enabled for FastAPI.")
    except Exception as exc:
        _set_telemetry_status(**base_status, status="error", reason=str(exc))
        logger.warning("Application Insights telemetry could not be enabled: %s", exc)


def add_request_telemetry_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_telemetry(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%s",
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.info(
            "request_completed method=%s path=%s status_code=%s duration_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        return response
