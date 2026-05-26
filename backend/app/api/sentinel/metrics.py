"""
Endpoints del Collector de Telemetría — Fase 3 DB Sentinel AI.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.sentinel_schemas import LiveMetricsResponse
from app.services.database_inventory import database_name_from_url, lab_mode_from_url, sentinel_database_name
from app.services.sentinel.collector_service import PostgresCollector
from app.services.sentinel.model_service import IncidentPredictorService
from app.services.sentinel.rca_service import RootCauseService

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

# Instancia global del collector (inicializada lazy)
_collector: Optional[PostgresCollector] = None
_collector_task: Optional[asyncio.Task] = None


def _get_collector() -> PostgresCollector:
    global _collector
    if _collector is None:
        if not settings.sentinel_monitor_db_url:
            raise HTTPException(
                status_code=503,
                detail="SENTINEL_MONITOR_DB_URL no está configurada en .env",
            )
        _collector = PostgresCollector(
            monitor_dsn=settings.sentinel_monitor_db_url,
            storage_dsn=settings.database_url,
            interval_seconds=settings.sentinel_collect_interval_seconds,
            database_name=sentinel_database_name(settings),
        )
    return _collector


async def start_auto_collection() -> None:
    """Arranca el collector periódico si está habilitado por configuración."""
    global _collector_task
    if not settings.sentinel_enable_auto_collect:
        return
    if _collector_task is not None and not _collector_task.done():
        return
    collector = _get_collector()
    _collector_task = asyncio.create_task(collector.run_continuous())


async def stop_auto_collection() -> None:
    """Detiene el collector periódico durante el apagado de FastAPI."""
    global _collector_task
    if _collector is not None:
        _collector.stop()
    if _collector_task is not None and not _collector_task.done():
        _collector_task.cancel()
        with suppress(asyncio.CancelledError):
            await _collector_task
    _collector_task = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/collect/trigger", summary="Dispara recolección manual inmediata")
async def trigger_collection() -> dict[str, Any]:
    """Ejecuta una recolección de telemetría ahora mismo sin esperar el intervalo."""
    collector = _get_collector()
    try:
        result = await collector.collect_once()
        return {"status": "collected", "sample": result}
    except Exception as exc:
        logger.exception("Error en recolección manual")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/collect/status", summary="Estado del collector")
def collect_status() -> dict[str, Any]:
    """Devuelve si el collector está activo y su configuración."""
    global _collector, _collector_task
    return {
        "initialized": _collector is not None,
        "running": _collector is not None and _collector._running,
        "interval_seconds": settings.sentinel_collect_interval_seconds,
        "monitor_db_configured": bool(settings.sentinel_monitor_db_url),
        "monitor_database_name": sentinel_database_name(settings),
        "monitor_lab_mode": lab_mode_from_url(settings.sentinel_monitor_db_url),
        "auto_collect_enabled": settings.sentinel_enable_auto_collect,
    }


@router.get("/status", summary="Estado integral de DB Sentinel AI")
def sentinel_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    total = db.execute(text("SELECT COUNT(*) FROM sentinel_metric_samples")).scalar()
    last = db.execute(text("SELECT collected_at FROM sentinel_metric_samples ORDER BY collected_at DESC LIMIT 1")).scalar()
    query_total = db.execute(text("SELECT COUNT(*) FROM sentinel_query_samples")).scalar()
    incident_total = db.execute(text("SELECT COUNT(*) FROM sentinel_incidents")).scalar()
    return {
        "environment": settings.environment,
        "storage_database_name": database_name_from_url(settings.database_url, "cloudapp"),
        "monitor_database_configured": bool(settings.sentinel_monitor_db_url),
        "monitor_database_name": sentinel_database_name(settings),
        "monitor_lab_mode": lab_mode_from_url(settings.sentinel_monitor_db_url),
        "auto_collect_enabled": settings.sentinel_enable_auto_collect,
        "collector_initialized": _collector is not None,
        "collector_running": _collector is not None and _collector._running,
        "collector_interval_seconds": settings.sentinel_collect_interval_seconds,
        "risk_threshold": settings.sentinel_risk_threshold,
        "total_samples": int(total or 0),
        "query_samples": int(query_total or 0),
        "incidents_total": int(incident_total or 0),
        "last_collected_at": last.isoformat() if last else None,
        "predictor": _predictor_status(),
        "rca": _rca_status(),
    }


@router.get(
    "/metrics/live",
    response_model=LiveMetricsResponse,
    summary="Última muestra de métricas",
)
def get_live_metrics(db: Session = Depends(get_db)) -> Any:
    """Retorna la muestra de telemetría más reciente almacenada."""
    row = db.execute(
        text(
            "SELECT * FROM sentinel_metric_samples ORDER BY collected_at DESC LIMIT 1"
        )
    ).fetchone()
    if row is None:
        return LiveMetricsResponse(message="No hay muestras disponibles. Ejecuta POST /sentinel/collect/trigger primero.")
    return dict(row._mapping)


@router.get("/metrics/history", summary="Historial de métricas")
def get_metrics_history(
    minutes: int = Query(default=60, ge=5, le=1440, description="Ventana de tiempo en minutos"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Serie temporal de métricas de los últimos N minutos."""
    since = datetime.utcnow() - timedelta(minutes=minutes)
    rows = db.execute(
        text("""
            SELECT
                collected_at, active_sessions, waiting_sessions,
                idle_in_transaction, lock_waiting_sessions,
                locks_granted, locks_waiting, long_transactions_count,
                cache_hit_ratio, xact_commit_delta, xact_rollback_delta,
                deadlocks_delta, wal_bytes_delta, replication_lag_seconds
            FROM sentinel_metric_samples
            WHERE collected_at > :since
            ORDER BY collected_at ASC
        """),
        {"since": since},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/metrics/queries", summary="Queries con mayor latencia")
def get_query_samples(
    minutes: int = Query(default=30, ge=5, le=360, description="Ventana de tiempo en minutos"),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Últimas muestras de queries ordenadas por latencia media descendente."""
    since = datetime.utcnow() - timedelta(minutes=minutes)
    rows = db.execute(
        text("""
            SELECT
                collected_at, queryid, query_fingerprint,
                calls_delta, mean_exec_time, stddev_exec_time, rows_delta, wal_bytes_delta
            FROM sentinel_query_samples
            WHERE collected_at > :since
            ORDER BY mean_exec_time DESC
            LIMIT 50
        """),
        {"since": since},
    ).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/metrics/summary", summary="Resumen rápido del estado actual")
def get_metrics_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Devuelve el conteo total de muestras y la última captura."""
    total = db.execute(
        text("SELECT COUNT(*) FROM sentinel_metric_samples")
    ).scalar()
    last = db.execute(
        text("SELECT collected_at FROM sentinel_metric_samples ORDER BY collected_at DESC LIMIT 1")
    ).scalar()
    return {
        "total_samples": total,
        "last_collected_at": last.isoformat() if last else None,
        "collector_interval_seconds": settings.sentinel_collect_interval_seconds,
    }


def _predictor_status() -> dict[str, Any]:
    path = Path(settings.sentinel_model_path)
    status = {"configured_path": str(path), "path_exists": path.exists(), "loaded": False, "model_version": None, "error": None}
    try:
        predictor = IncidentPredictorService.get_instance(settings.sentinel_model_path, settings.sentinel_feature_schema_path)
        status.update({"loaded": True, "model_version": predictor.model_version, "feature_count": len(predictor.feature_cols)})
    except Exception as exc:
        status["error"] = str(exc)
    return status


def _rca_status() -> dict[str, Any]:
    path = Path(settings.sentinel_rca_model_path)
    status = {"configured_path": str(path), "path_exists": path.exists(), "loaded": False, "model_version": None, "error": None}
    try:
        rca = RootCauseService.get_instance(settings.sentinel_rca_model_path)
        status.update({"loaded": True, "model_version": rca.model_version, "feature_count": len(rca.feature_cols)})
    except Exception as exc:
        status["error"] = str(exc)
    return status
