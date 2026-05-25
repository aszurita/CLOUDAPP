"""DB Sentinel AI database engine adapters."""
from __future__ import annotations

from app.services.sentinel.adapters.base_adapter import (
    CANONICAL_METRIC_FIELDS,
    BaseDBAdapter,
    CanonicalMetrics,
    QuerySample,
)
from app.services.sentinel.adapters.mysql_adapter import MySQLAdapter
from app.services.sentinel.adapters.postgres_adapter import PostgresAdapter
from app.services.sentinel.adapters.sqlserver_adapter import SQLServerAdapter

ADAPTER_REGISTRY: dict[str, type[BaseDBAdapter]] = {
    "postgresql": PostgresAdapter,
    "postgres": PostgresAdapter,
    "sqlserver": SQLServerAdapter,
    "mssql": SQLServerAdapter,
    "mysql": MySQLAdapter,
}

ENGINE_STATUS = {
    "postgresql": {
        "status": "stable",
        "features": ["full_telemetry", "query_fingerprints", "ml_prediction", "fault_lab"],
    },
    "sqlserver": {
        "status": "beta",
        "features": ["canonical_telemetry", "query_stats", "ml_prediction"],
    },
    "mysql": {
        "status": "beta",
        "features": ["canonical_telemetry", "statement_digest", "ml_prediction"],
    },
}


def normalize_engine(engine: str) -> str:
    normalized = engine.strip().lower()
    if normalized == "postgres":
        return "postgresql"
    if normalized == "mssql":
        return "sqlserver"
    return normalized


def get_adapter(engine: str, connection_string: str, database_name: str) -> BaseDBAdapter:
    normalized = normalize_engine(engine)
    adapter_cls = ADAPTER_REGISTRY.get(normalized)
    if adapter_cls is None:
        supported = sorted(set(normalize_engine(key) for key in ADAPTER_REGISTRY))
        raise ValueError(f"Motor no soportado: {engine}. Opciones: {supported}")
    return adapter_cls(connection_string=connection_string, database_name=database_name)


def supported_engines() -> list[dict[str, object]]:
    engines = []
    for engine, status in ENGINE_STATUS.items():
        engines.append(
            {
                "id": engine,
                **status,
                "canonical_metric_count": len(CANONICAL_METRIC_FIELDS),
                "canonical_metrics": CANONICAL_METRIC_FIELDS,
            }
        )
    return engines


__all__ = [
    "ADAPTER_REGISTRY",
    "CANONICAL_METRIC_FIELDS",
    "BaseDBAdapter",
    "CanonicalMetrics",
    "ENGINE_STATUS",
    "MySQLAdapter",
    "PostgresAdapter",
    "QuerySample",
    "SQLServerAdapter",
    "get_adapter",
    "normalize_engine",
    "supported_engines",
]
