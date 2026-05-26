from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings
from app.db.session import engine as app_engine
from app.services.query_governance import ALLOWED_QUERY_TABLES, INTERNAL_TABLES, SENSITIVE_TERMS


SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "pgbouncer", "azure_sys", "cron"}


@dataclass(frozen=True)
class DatabaseSource:
    key: str
    label: str
    role: str
    engine: Engine
    url: str | None = None


def database_name_from_url(url: str | None, fallback: str = "unknown") -> str:
    if not url:
        return fallback
    parsed = urlparse(_normalized_driver_url(url))
    database = parsed.path.lstrip("/")
    return database or fallback


def host_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(_normalized_driver_url(url)).hostname


def lab_mode_from_url(url: str | None) -> str:
    host = host_from_url(url)
    if not host:
        return "not_configured"
    if host in {"localhost", "127.0.0.1", "postgres"}:
        return "local_lab"
    return "azure_demo"


def sentinel_database_name(settings: Settings | None = None) -> str:
    current = settings or get_settings()
    if current.sentinel_monitor_database_name:
        return current.sentinel_monitor_database_name
    return database_name_from_url(current.sentinel_monitor_db_url, "core_banking_sim")


def collect_database_inventory(settings: Settings | None = None) -> dict:
    current = settings or get_settings()
    sources = [_application_source(current)]
    if current.sentinel_monitor_db_url:
        sources.append(_monitor_source(current))

    payload = {
        "environment": current.environment,
        "sources": [],
    }
    for source in sources:
        payload["sources"].append(_inspect_source(source))
    return payload


def _application_source(settings: Settings) -> DatabaseSource:
    return DatabaseSource(
        key="cloudapp",
        label=database_name_from_url(settings.database_url, "cloudapp"),
        role="application",
        engine=app_engine,
        url=settings.database_url,
    )


def _monitor_source(settings: Settings) -> DatabaseSource:
    engine = create_engine(settings.sentinel_monitor_db_url, pool_pre_ping=True)
    return DatabaseSource(
        key="sentinel_monitor",
        label=sentinel_database_name(settings),
        role="monitored_database",
        engine=engine,
        url=settings.sentinel_monitor_db_url,
    )


def _inspect_source(source: DatabaseSource) -> dict:
    parsed_host = host_from_url(source.url)
    result = {
        "key": source.key,
        "label": source.label,
        "role": source.role,
        "engine": source.engine.dialect.name,
        "host": parsed_host,
        "database_name": source.label,
        "lab_mode": lab_mode_from_url(source.url) if source.role == "monitored_database" else "application",
        "status": "available",
        "error": None,
        "schemas": [],
    }
    try:
        inspector = inspect(source.engine)
        schema_names = _schema_names(source.engine, inspector)
        for schema_name in schema_names:
            tables = []
            for table_name in inspector.get_table_names(schema=schema_name):
                columns = [
                    {
                        "name": str(column["name"]),
                        "type": str(column["type"]),
                        "nullable": bool(column.get("nullable", True)),
                        "sensitive": _is_sensitive_column(str(column["name"])),
                    }
                    for column in inspector.get_columns(table_name, schema=schema_name)
                ]
                is_internal = table_name in INTERNAL_TABLES or table_name.startswith(("alembic_", "sqlite_"))
                allowed_query = source.role == "application" and table_name in ALLOWED_QUERY_TABLES
                tables.append(
                    {
                        "name": table_name,
                        "schema_name": schema_name or "main",
                        "qualified_name": _qualified_name(source.label, schema_name, table_name),
                        "column_count": len(columns),
                        "columns": columns,
                        "allowed_query": allowed_query,
                        "internal": is_internal,
                        "source_role": source.role,
                    }
                )
            result["schemas"].append(
                {
                    "name": schema_name or "main",
                    "tables": sorted(tables, key=lambda table: table["name"]),
                }
            )
        result["schemas"] = [schema for schema in result["schemas"] if schema["tables"]]
        result["table_count"] = sum(len(schema["tables"]) for schema in result["schemas"])
        result["queryable_table_count"] = sum(
            1 for schema in result["schemas"] for table in schema["tables"] if table["allowed_query"]
        )
    except Exception as exc:
        result["status"] = "unavailable"
        result["error"] = str(exc)
        result["table_count"] = 0
        result["queryable_table_count"] = 0
    finally:
        if source.role == "monitored_database":
            source.engine.dispose()
    return result


def _schema_names(engine: Engine, inspector) -> list[str | None]:
    if engine.dialect.name == "sqlite":
        return [None]
    names = [schema for schema in inspector.get_schema_names() if schema not in SYSTEM_SCHEMAS]
    return names or ["public"]


def _qualified_name(database_name: str, schema_name: str | None, table_name: str) -> str:
    schema = schema_name or "main"
    return f"{database_name}.{schema}.{table_name}"


def _is_sensitive_column(column_name: str) -> bool:
    lowered = column_name.lower()
    return any(term in lowered for term in SENSITIVE_TERMS)


def _normalized_driver_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)
