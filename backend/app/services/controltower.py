from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter, sleep
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.telemetry import get_telemetry_status
from app.db.session import engine as app_engine
from app.models import AuditEvent, CatalogAsset
from app.services.database_inventory import SYSTEM_SCHEMAS, database_name_from_url, host_from_url

logger = logging.getLogger(__name__)
AZURE_POSTGRES_CONNECT_TIMEOUT_SECONDS = 3


@dataclass(frozen=True)
class TowerSourceConfig:
    id: str
    name: str
    source_type: str
    engine_name: str
    environment: str
    url: str | None
    host: str | None
    port: int | None
    database_name: str | None
    username: str | None
    secret_ref: str | None
    docker_container_name: str | None
    cloud_provider: str
    telemetry_provider: str
    badges: list[str]
    message: str | None = None


class ControlTowerService:
    title = "Database Control Tower AI"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def endpoints(self) -> list[dict[str, str]]:
        return [
            {"method": "GET", "path": "/api/controltower", "description": "Titulo y mapa de endpoints Control Tower."},
            {"method": "GET", "path": "/api/controltower/database-sources", "description": "Lista fuentes monitoreadas y estado actual."},
            {"method": "GET", "path": "/api/controltower/database-sources/{source_id}", "description": "Detalle tecnico de una fuente."},
            {"method": "POST", "path": "/api/controltower/database-sources/{source_id}/test-connection", "description": "Prueba conexion sin exponer secretos."},
            {"method": "POST", "path": "/api/controltower/database-sources/{source_id}/refresh", "description": "Recolecta metricas en vivo de la fuente."},
            {"method": "GET", "path": "/api/controltower/database-sources/{source_id}/metrics", "description": "Metricas SQL actuales."},
            {"method": "GET", "path": "/api/controltower/database-sources/{source_id}/databases", "description": "Bases visibles dentro del servidor PostgreSQL."},
            {"method": "GET", "path": "/api/controltower/database-sources/{source_id}/tables", "description": "Inventario real de tablas."},
            {"method": "GET", "path": "/api/controltower/database-sources/{source_id}/sessions", "description": "Sesiones PostgreSQL activas/idle/waiting."},
            {"method": "GET", "path": "/api/controltower/database-sources/{source_id}/locks", "description": "Locks PostgreSQL agrupados."},
            {"method": "GET", "path": "/api/controltower/dashboard/database-overview", "description": "Overview agregado para cards."},
            {"method": "GET", "path": "/api/controltower/dashboard/health-summary", "description": "Score global, estados y recomendaciones."},
            {"method": "GET", "path": "/api/controltower/dashboard/cloud-integrations", "description": "Key Vault, App Insights, Azure Monitor y Databricks."},
            {"method": "GET", "path": "/api/controltower/databricks/catalogs", "description": "Catalogos/esquemas/tablas Databricks disponibles."},
            {"method": "GET", "path": "/api/controltower/databricks/schemas", "description": "Schemas Databricks detectados."},
            {"method": "GET", "path": "/api/controltower/databricks/tables", "description": "Tablas Databricks detectadas."},
            {"method": "GET", "path": "/api/controltower/azure/keyvault/status", "description": "Estado de configuracion Key Vault."},
            {"method": "GET", "path": "/api/controltower/azure/postgres/{source_id}/metrics", "description": "Metricas SQL/Azure para PostgreSQL cloud."},
            {"method": "GET", "path": "/api/controltower/telemetry/backend-summary", "description": "Resumen local de telemetria/auditoria backend."},
            {"method": "GET", "path": "/api/controltower/recommendations", "description": "Recomendaciones DBA basadas en reglas."},
            {"method": "GET", "path": "/api/controltower/history", "description": "Historico disponible y ultimos snapshots."},
        ]

    def source_configs(self) -> list[TowerSourceConfig]:
        return [
            self._cloudapp_source(),
            self._sentinel_source(),
            self._azure_postgres_source(),
            self._databricks_source(),
            self._controltower_source(),
        ]

    def source_config(self, source_id: str) -> TowerSourceConfig | None:
        return next((source for source in self.source_configs() if source.id == source_id), None)

    def overview(self) -> dict[str, Any]:
        sources = self.sources(include_metrics=True)
        health_scores = [
            source["metric_snapshot"]["health_score"]
            for source in sources
            if source.get("metric_snapshot") and source["status"] != "pending"
        ]
        health_global = round(sum(health_scores) / len(health_scores)) if health_scores else 0
        recommendations = self.recommendations(sources=sources)
        return {
            "title": self.title,
            "environment": self.settings.environment,
            "health_global": health_global,
            "sources_total": len(sources),
            "online_sources": sum(1 for source in sources if source["status"] == "online"),
            "local_docker_dbs": sum(
                source.get("databases_count") or 1
                for source in sources
                if source["source_type"] in {"docker_database", "system_database"}
            ),
            "cloud_dbs": sum(source.get("databases_count") or 1 for source in sources if source["source_type"] == "cloud_database"),
            "lakehouses": sum(1 for source in sources if source["source_type"] == "lakehouse"),
            "active_alerts": sum(1 for item in recommendations if item["severity"] in {"critical", "high"}),
            "sources": sources,
        }

    def sources(self, include_metrics: bool = True) -> list[dict[str, Any]]:
        return [self.source_payload(config, include_metrics=include_metrics) for config in self.source_configs()]

    def source_payload(self, config: TowerSourceConfig, include_metrics: bool = True) -> dict[str, Any]:
        configured = self._is_configured(config)
        snapshot = None
        status = "pending" if not configured else "online"
        message = config.message
        if include_metrics and configured and config.engine_name == "postgresql":
            snapshot = self.metrics(config.id)
            status = snapshot["status"]
            message = snapshot.get("error") or message
        elif config.engine_name == "databricks":
            status = "online" if self.settings.databricks_host and self.settings.databricks_token else "pending"
            snapshot = self._databricks_snapshot(status)
            message = None if status == "online" else "Configure DATABRICKS_HOST and DATABRICKS_TOKEN."
        databases: list[dict[str, Any]] = []
        if configured and config.engine_name == "postgresql" and status != "offline":
            databases = self.databases(config.id)
            if not databases and config.database_name:
                databases = [self._database_fallback(config)]

        return {
            "id": config.id,
            "name": config.name,
            "source_type": config.source_type,
            "engine": config.engine_name,
            "environment": config.environment,
            "host": config.host,
            "port": config.port,
            "database_name": config.database_name,
            "username": config.username,
            "secret_ref": config.secret_ref,
            "docker_container_name": config.docker_container_name,
            "cloud_provider": config.cloud_provider,
            "telemetry_provider": config.telemetry_provider,
            "badges": config.badges,
            "status": status,
            "connection_configured": configured,
            "metric_snapshot": snapshot,
            "databases_count": len(databases),
            "databases": databases,
            "message": message,
        }

    def test_connection(self, source_id: str) -> dict[str, Any]:
        config = self._source_or_error(source_id)
        if config.engine_name == "databricks":
            configured = bool(self.settings.databricks_host and self.settings.databricks_token)
            return {
                "source_id": source_id,
                "success": configured,
                "status": "connected" if configured else "pending",
                "message": "Databricks host/token configured." if configured else "Missing Databricks host or token.",
            }
        if not self._is_configured(config):
            return {"source_id": source_id, "success": False, "status": "pending", "message": config.message or "Connection is not configured."}
        try:
            engine = self._engine_for(config)
            started = perf_counter()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            latency_ms = round((perf_counter() - started) * 1000, 2)
            return {"source_id": source_id, "success": True, "status": "connected", "latency_ms": latency_ms}
        except Exception as exc:
            logger.warning("Control Tower connection test failed for %s: %s", source_id, exc)
            return {"source_id": source_id, "success": False, "status": "unavailable", "message": str(exc)}
        finally:
            if config.id != "cloudapp_postgres":
                try:
                    engine.dispose()
                except Exception:
                    pass

    def metrics(self, source_id: str) -> dict[str, Any]:
        config = self._source_or_error(source_id)
        if config.engine_name != "postgresql":
            return self._databricks_snapshot("online" if self.settings.databricks_host else "pending")
        if not self._is_configured(config):
            return self._empty_snapshot("pending", 0, config.message or "Connection is not configured.")

        engine = self._engine_for(config)
        try:
            started = perf_counter()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                latency_ms = round((perf_counter() - started) * 1000, 2)
                if engine.dialect.name != "postgresql":
                    return self._empty_snapshot("online", 100, None, latency_ms=latency_ms)
                row = connection.execute(
                    text(
                        """
                        SELECT
                          (SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'active') AS active_connections,
                          (SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database()) AS total_connections,
                          (SELECT COUNT(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle') AS idle_connections,
                          (SELECT COUNT(*) FROM pg_locks l WHERE l.database = (SELECT oid FROM pg_database WHERE datname = current_database()) OR l.database IS NULL) AS locks_count,
                          pg_database_size(current_database()) AS database_size_bytes,
                          (SELECT COUNT(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema')) AS tables_count,
                          sd.xact_commit,
                          sd.xact_rollback,
                          sd.deadlocks,
                          CASE
                            WHEN (sd.blks_hit + sd.blks_read) = 0 THEN NULL
                            ELSE ROUND((sd.blks_hit::numeric / NULLIF(sd.blks_hit + sd.blks_read, 0)) * 100, 4)
                          END AS cache_hit_ratio
                        FROM pg_stat_database sd
                        WHERE sd.datname = current_database()
                        """
                    )
                ).mappings().first()
            snapshot = {
                "status": "online",
                "latency_ms": latency_ms,
                "active_connections": int(row["active_connections"] or 0),
                "total_connections": int(row["total_connections"] or 0),
                "idle_connections": int(row["idle_connections"] or 0),
                "database_size_bytes": int(row["database_size_bytes"] or 0),
                "tables_count": int(row["tables_count"] or 0),
                "locks_count": int(row["locks_count"] or 0),
                "cache_hit_ratio": float(row["cache_hit_ratio"]) if row["cache_hit_ratio"] is not None else None,
                "xact_commit": int(row["xact_commit"] or 0),
                "xact_rollback": int(row["xact_rollback"] or 0),
                "deadlocks": int(row["deadlocks"] or 0),
                "captured_at": self._now(),
                "error": None,
            }
            snapshot["health_score"] = self._health_score(snapshot, config)
            snapshot["status"] = "degraded" if snapshot["health_score"] < 90 else "online"
            self._store_metric_snapshot(config, snapshot)
            return snapshot
        except Exception as exc:
            logger.warning("Control Tower metrics failed for %s: %s", source_id, exc)
            return self._empty_snapshot("offline", 0, str(exc))
        finally:
            if config.id != "cloudapp_postgres":
                engine.dispose()

    def databases(self, source_id: str) -> list[dict[str, Any]]:
        config = self._source_or_error(source_id)
        if config.engine_name != "postgresql" or not self._is_configured(config):
            return []
        engine = self._engine_for(config)
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                          d.datname AS database_name,
                          pg_catalog.pg_get_userbyid(d.datdba) AS owner,
                          pg_catalog.pg_encoding_to_char(d.encoding) AS encoding,
                          d.datistemplate AS is_template,
                          d.datallowconn AS allow_connections,
                          CASE WHEN d.datallowconn THEN pg_catalog.pg_database_size(d.datname) ELSE NULL END AS size_bytes,
                          (
                            SELECT COUNT(*)::int
                            FROM pg_stat_activity a
                            WHERE a.datname = d.datname AND a.state = 'active'
                          ) AS active_connections,
                          (
                            SELECT COUNT(*)::int
                            FROM pg_stat_activity a
                            WHERE a.datname = d.datname
                          ) AS total_connections,
                          d.datname = current_database() AS is_current,
                          (
                            d.datname IN ('postgres', 'azure_sys', 'azure_maintenance')
                            OR d.datname LIKE 'template%%'
                          ) AS is_system
                        FROM pg_database d
                        WHERE NOT d.datistemplate
                        ORDER BY is_system ASC, d.datname ASC
                        """
                    )
                ).mappings().all()
            return [
                {
                    "source_id": source_id,
                    "database_name": str(row["database_name"]),
                    "owner": row["owner"],
                    "encoding": row["encoding"],
                    "is_template": bool(row["is_template"]),
                    "allow_connections": bool(row["allow_connections"]),
                    "size_bytes": int(row["size_bytes"]) if row["size_bytes"] is not None else None,
                    "active_connections": int(row["active_connections"] or 0),
                    "total_connections": int(row["total_connections"] or 0),
                    "is_current": bool(row["is_current"]),
                    "is_system": bool(row["is_system"]),
                }
                for row in rows
            ]
        except Exception:
            if config.source_type == "cloud_database" or not config.database_name:
                return []
            return [self._database_fallback(config)]
        finally:
            if config.id != "cloudapp_postgres":
                engine.dispose()

    def tables(self, source_id: str) -> list[dict[str, Any]]:
        config = self._source_or_error(source_id)
        if config.engine_name == "databricks":
            return self._try_databricks_live_tables() or self._databricks_tables_from_catalog()
        if not self._is_configured(config):
            return []
        engine = self._engine_for(config)
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                          schemaname AS schema_name,
                          relname AS table_name,
                          n_live_tup::bigint AS estimated_rows,
                          pg_total_relation_size(relid)::bigint AS size_bytes,
                          'table' AS table_type
                        FROM pg_stat_user_tables
                        ORDER BY pg_total_relation_size(relid) DESC, schemaname, relname
                        LIMIT 250
                        """
                    )
                ).mappings().all()
            return [
                {
                    "source_id": source_id,
                    "schema_name": str(row["schema_name"]),
                    "table_name": str(row["table_name"]),
                    "estimated_rows": int(row["estimated_rows"] or 0),
                    "size_bytes": int(row["size_bytes"] or 0),
                    "table_type": str(row["table_type"]),
                    "last_seen_at": self._now(),
                }
                for row in rows
            ]
        except Exception:
            return self._tables_from_inspector(config, engine)
        finally:
            if config.id != "cloudapp_postgres":
                engine.dispose()

    def sessions(self, source_id: str) -> list[dict[str, Any]]:
        config = self._source_or_error(source_id)
        if config.engine_name != "postgresql" or not self._is_configured(config):
            return []
        engine = self._engine_for(config)
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                          pid,
                          usename AS username,
                          state,
                          wait_event_type,
                          wait_event,
                          query_start,
                          LEFT(query, 240) AS query
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                        ORDER BY query_start DESC NULLS LAST, pid
                        LIMIT 80
                        """
                    )
                ).mappings().all()
            return [_json_safe_dict(row) for row in rows]
        except Exception:
            return []
        finally:
            if config.id != "cloudapp_postgres":
                engine.dispose()

    def locks(self, source_id: str) -> list[dict[str, Any]]:
        config = self._source_or_error(source_id)
        if config.engine_name != "postgresql" or not self._is_configured(config):
            return []
        engine = self._engine_for(config)
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        """
                        SELECT
                          locktype,
                          relation::regclass::text AS relation_name,
                          mode,
                          granted,
                          COUNT(*)::int AS lock_count
                        FROM pg_locks
                        WHERE database = (SELECT oid FROM pg_database WHERE datname = current_database())
                           OR database IS NULL
                        GROUP BY locktype, relation, mode, granted
                        ORDER BY granted ASC, lock_count DESC
                        LIMIT 80
                        """
                    )
                ).mappings().all()
            return [_json_safe_dict(row) for row in rows]
        except Exception:
            return []
        finally:
            if config.id != "cloudapp_postgres":
                engine.dispose()

    def integrations(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "key-vault",
                "name": "Azure Key Vault",
                "provider": "Azure",
                "status": "configured" if self.settings.azure_key_vault_url else "pending",
                "signal": "Secret resolver",
                "description": "Passwords, tokens and connection strings stay out of React.",
                "required_settings": ["AZURE_KEY_VAULT_URL"],
            },
            {
                "id": "application-insights",
                "name": "Application Insights",
                "provider": "Azure",
                "status": "configured" if self.settings.applicationinsights_connection_string else "pending",
                "signal": "Backend telemetry",
                "description": "FastAPI requests, errors, timings and health checks.",
                "required_settings": ["APPLICATIONINSIGHTS_CONNECTION_STRING"],
            },
            {
                "id": "azure-monitor",
                "name": "Azure Monitor",
                "provider": "Azure",
                "status": "configured" if self.settings.azure_postgres_resource_id else "pending",
                "signal": "Native cloud metrics",
                "description": "CPU, storage, I/O and connection metrics for Azure PostgreSQL.",
                "required_settings": ["AZURE_POSTGRES_RESOURCE_ID"],
            },
            {
                "id": "databricks",
                "name": "Databricks SQL Warehouse",
                "provider": "Databricks",
                "status": "configured" if self.settings.databricks_host and self.settings.databricks_token else "pending",
                "signal": "Lakehouse metadata",
                "description": "Catalogs, schemas, tables and SQL Warehouse statement execution.",
                "required_settings": ["DATABRICKS_HOST", "DATABRICKS_TOKEN", "DATABRICKS_SQL_WAREHOUSE_ID"],
            },
            {
                "id": "local-postgres",
                "name": "Local Docker PostgreSQL",
                "provider": "Local",
                "status": "connected" if self.settings.database_url and self.settings.sentinel_monitor_db_url else "pending",
                "signal": "localhost SQL checks",
                "description": "cloudapp_postgres, sentinel_postgres and optional controltower_postgres.",
                "required_settings": ["DATABASE_URL", "SENTINEL_MONITOR_DB_URL", "CONTROLTOWER_DATABASE_URL"],
            },
        ]

    def recommendations(self, sources: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        current_sources = sources or self.sources(include_metrics=True)
        output: list[dict[str, Any]] = []
        local_latencies = [
            source["metric_snapshot"]["latency_ms"]
            for source in current_sources
            if source["source_type"] in {"docker_database", "system_database"}
            and source.get("metric_snapshot")
            and source["metric_snapshot"].get("latency_ms") is not None
        ]
        local_avg = sum(local_latencies) / len(local_latencies) if local_latencies else 0
        for source in current_sources:
            snapshot = source.get("metric_snapshot") or {}
            if source["status"] in {"offline", "pending"}:
                output.append(
                    self._recommendation(
                        source,
                        "medium",
                        "Configuration",
                        "Fuente sin conexion activa en Control Tower",
                        "Configurar el secreto o variable de entorno requerida y ejecutar test-connection.",
                        source.get("message") or "La fuente no devolvio metricas en vivo.",
                        "Sin conexion no hay snapshots, health score ni alertas confiables.",
                        "configuration",
                    )
                )
                continue
            latency = snapshot.get("latency_ms")
            if source["source_type"] == "cloud_database" and latency and local_avg and latency > local_avg * 3:
                output.append(
                    self._recommendation(
                        source,
                        "medium",
                        "Latency",
                        "Azure PostgreSQL tiene mayor latencia que las bases locales",
                        "Revisar region, SSL, red, carga del flexible server y metricas de Azure Monitor.",
                        f"Latencia {latency} ms frente a promedio local {local_avg:.1f} ms.",
                        "Puede afectar operaciones cloud y dashboards ejecutivos.",
                        "read_only",
                    )
                )
            locks_count = snapshot.get("locks_count") or 0
            if locks_count > 0 and source["engine"] == "postgresql":
                severity = "high" if locks_count > 25 else "medium"
                output.append(
                    self._recommendation(
                        source,
                        severity,
                        "Locks",
                        "Locks detectados en PostgreSQL",
                        "Revisar sesiones, queries bloqueantes y duracion de transacciones.",
                        f"locks_count={locks_count}.",
                        "Puede generar esperas, timeouts o incidentes tipo deadlock.",
                        "approval_required",
                    )
                )
            total_connections = snapshot.get("total_connections") or 0
            if total_connections > 80:
                output.append(
                    self._recommendation(
                        source,
                        "medium",
                        "Connections",
                        "Conexiones altas en la fuente",
                        "Revisar pooling, sesiones idle y limites de conexion.",
                        f"total_connections={total_connections}.",
                        "La saturacion de conexiones puede degradar latencia y disponibilidad.",
                        "read_only",
                    )
                )

        if self.settings.databricks_host and self.settings.databricks_token:
            output.append(
                {
                    "id": "rec-databricks-lakehouse-curation",
                    "source_id": "databricks_lakehouse",
                    "severity": "low",
                    "category": "Lakehouse",
                    "title": "Validar capas Bronze, Silver y Gold",
                    "recommendation": "Listar tablas por schema y priorizar modelos Gold para consumo ejecutivo.",
                    "evidence": f"Catalogo configurado: {self.settings.databricks_catalog}.",
                    "impact": "Mejora el valor analitico del Control Tower.",
                    "action_type": "configuration",
                }
            )
        return output

    def databricks_catalog(self, db: Session) -> dict[str, Any]:
        configured = bool(self.settings.databricks_host and self.settings.databricks_token)
        warehouse_configured = bool(self.settings.databricks_sql_warehouse_id)
        schemas = [
            self.settings.databricks_schema_bronze,
            self.settings.databricks_schema_silver,
            self.settings.databricks_schema_gold,
            "banco_demo",
        ]
        tables = self._databricks_tables_from_db(db)
        message = None
        if configured and warehouse_configured:
            live = self._try_databricks_live_tables()
            if live:
                schemas = sorted({str(item.get("schema_name") or item.get("schema") or "") for item in live if item.get("schema_name") or item.get("schema")})
                tables = live
            else:
                message = "Databricks SQL Warehouse configured, but live query did not return tables. Using catalog cache if available."
        elif not configured:
            message = "Configure DATABRICKS_HOST and DATABRICKS_TOKEN to query live Databricks metadata."
        elif not warehouse_configured:
            message = "Configure DATABRICKS_SQL_WAREHOUSE_ID to run Statement Execution API queries."
        return {
            "configured": configured,
            "host_configured": bool(self.settings.databricks_host),
            "token_configured": bool(self.settings.databricks_token),
            "warehouse_configured": warehouse_configured,
            "catalog": self.settings.databricks_catalog,
            "schemas": sorted(set(filter(None, schemas))),
            "tables": tables,
            "message": message,
        }

    def telemetry_summary(self, db: Session) -> dict[str, Any]:
        total = db.query(AuditEvent).count()
        latest = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(10).all()
        telemetry_status = get_telemetry_status()
        return {
            "application_insights_configured": bool(self.settings.applicationinsights_connection_string),
            "application_insights_enabled": telemetry_status["enabled"],
            "application_insights_status": telemetry_status["status"],
            "application_insights_reason": telemetry_status["reason"],
            "application_insights_connection": telemetry_status["connection"],
            "application_insights_dependencies": telemetry_status["dependencies"],
            "application_insights_live_metrics_enabled": telemetry_status["live_metrics_enabled"],
            "outbound_proxy": telemetry_status["proxy"],
            "log_analytics_configured": bool(self.settings.applicationinsights_connection_string),
            "audit_events_total": total,
            "latest_events": [
                {
                    "event_type": item.event_type,
                    "severity": item.severity,
                    "message": item.message,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                }
                for item in latest
            ],
        }

    def history(self) -> dict[str, Any]:
        if self.settings.controltower_database_url:
            engine: Engine | None = None
            try:
                engine = create_engine(self.settings.controltower_database_url, pool_pre_ping=True)
                with engine.connect() as connection:
                    rows = connection.execute(
                        text(
                            """
                            SELECT
                              source_id,
                              captured_at,
                              health_score,
                              status,
                              latency_ms,
                              total_connections,
                              locks_count,
                              cache_hit_ratio
                            FROM source_metric_snapshots
                            ORDER BY captured_at DESC
                            LIMIT 80
                            """
                        )
                    ).mappings().all()
                engine.dispose()
                return {
                    "mode": "persistent",
                    "message": "History is stored in controltower_postgres.source_metric_snapshots.",
                    "snapshots": [_json_safe_dict(row) for row in rows],
                }
            except Exception as exc:
                if engine is not None:
                    try:
                        engine.dispose()
                    except Exception:
                        pass
                return {
                    "mode": "persistent_unavailable",
                    "message": f"CONTROLTOWER_DATABASE_URL is configured but history is not readable: {exc}",
                    "snapshots": [],
                }
        sources = self.sources(include_metrics=True)
        return {
            "mode": "live_snapshot",
            "message": "Persistent history requires CONTROLTOWER_DATABASE_URL and snapshot tables from the execution plan.",
            "snapshots": [
                {
                    "source_id": source["id"],
                    "captured_at": (source.get("metric_snapshot") or {}).get("captured_at"),
                    "health_score": (source.get("metric_snapshot") or {}).get("health_score"),
                    "status": source["status"],
                }
                for source in sources
            ],
        }

    def _source_or_error(self, source_id: str) -> TowerSourceConfig:
        config = self.source_config(source_id)
        if not config:
            raise ValueError(f"Unknown Control Tower source: {source_id}")
        return config

    def _cloudapp_source(self) -> TowerSourceConfig:
        return TowerSourceConfig(
            id="cloudapp_postgres",
            name="cloudapp_postgres",
            source_type="docker_database",
            engine_name="postgresql",
            environment=self.settings.environment,
            url=self.settings.database_url,
            host=host_from_url(self.settings.database_url) or "localhost",
            port=_port_from_url(self.settings.database_url, 5432),
            database_name=database_name_from_url(self.settings.database_url, "cloudapp"),
            username=_username_from_url(self.settings.database_url),
            secret_ref="DATABASE_URL",
            docker_container_name="cloudapp_postgres",
            cloud_provider="none",
            telemetry_provider="Application Insights",
            badges=["Docker", "PostgreSQL", "App DB"],
        )

    def _sentinel_source(self) -> TowerSourceConfig:
        return TowerSourceConfig(
            id="sentinel_postgres",
            name="sentinel_postgres",
            source_type="docker_database",
            engine_name="postgresql",
            environment="local",
            url=self.settings.sentinel_monitor_db_url,
            host=host_from_url(self.settings.sentinel_monitor_db_url) or "localhost",
            port=_port_from_url(self.settings.sentinel_monitor_db_url, 5433),
            database_name=database_name_from_url(self.settings.sentinel_monitor_db_url, "core_banking_sim"),
            username=_username_from_url(self.settings.sentinel_monitor_db_url),
            secret_ref="SENTINEL_MONITOR_DB_URL",
            docker_container_name="sentinel_postgres",
            cloud_provider="none",
            telemetry_provider="Application Insights",
            badges=["Docker", "PostgreSQL", "Sentinel Lab"],
            message=None if self.settings.sentinel_monitor_db_url else "Configure SENTINEL_MONITOR_DB_URL.",
        )

    def _azure_postgres_source(self) -> TowerSourceConfig:
        url = self._azure_postgres_url()
        return TowerSourceConfig(
            id="azure_postgres_cloudapp",
            name="azure_postgres_cloudapp",
            source_type="cloud_database",
            engine_name="postgresql",
            environment="azure-dev",
            url=url,
            host=self.settings.azure_postgres_host,
            port=self.settings.azure_postgres_port,
            database_name=self.settings.azure_postgres_db,
            username=self.settings.azure_postgres_user,
            secret_ref="AZURE_POSTGRES_PASSWORD",
            docker_container_name=None,
            cloud_provider="azure",
            telemetry_provider="Azure Monitor",
            badges=["Azure", "PostgreSQL", "SSL", "Azure Monitor"],
            message=None if url else "Configure AZURE_POSTGRES_HOST, AZURE_POSTGRES_USER and AZURE_POSTGRES_PASSWORD.",
        )

    def _databricks_source(self) -> TowerSourceConfig:
        return TowerSourceConfig(
            id="databricks_lakehouse",
            name="databricks_lakehouse",
            source_type="lakehouse",
            engine_name="databricks",
            environment="cloud",
            url=None,
            host=self.settings.databricks_host,
            port=443,
            database_name=self.settings.databricks_catalog,
            username="token" if self.settings.databricks_token else None,
            secret_ref="DATABRICKS_TOKEN",
            docker_container_name=None,
            cloud_provider="azure",
            telemetry_provider="Databricks",
            badges=["Databricks", "Lakehouse", "SQL Warehouse"],
            message=None if self.settings.databricks_host and self.settings.databricks_token else "Configure DATABRICKS_HOST and DATABRICKS_TOKEN.",
        )

    def _controltower_source(self) -> TowerSourceConfig:
        return TowerSourceConfig(
            id="controltower_postgres",
            name="controltower_postgres",
            source_type="system_database",
            engine_name="postgresql",
            environment="local",
            url=self.settings.controltower_database_url,
            host=host_from_url(self.settings.controltower_database_url) or "localhost",
            port=_port_from_url(self.settings.controltower_database_url, 5440),
            database_name=database_name_from_url(self.settings.controltower_database_url, "controltower"),
            username=_username_from_url(self.settings.controltower_database_url),
            secret_ref="CONTROLTOWER_DATABASE_URL",
            docker_container_name="controltower_postgres",
            cloud_provider="none",
            telemetry_provider="Application Insights",
            badges=["Docker", "PostgreSQL", "System DB"],
            message=None if self.settings.controltower_database_url else "Configure CONTROLTOWER_DATABASE_URL after creating controltower_postgres.",
        )

    def _azure_postgres_url(self) -> str | None:
        if not (self.settings.azure_postgres_host and self.settings.azure_postgres_user and self.settings.azure_postgres_password):
            return None
        user = quote(self.settings.azure_postgres_user, safe="")
        raw_password = self.settings.azure_postgres_password
        if _has_percent_escape(raw_password):
            raw_password = unquote(raw_password)
        password = quote(raw_password, safe="")
        db = quote(self.settings.azure_postgres_db or "cloudapp", safe="")
        sslmode = quote(self.settings.azure_postgres_sslmode or "require", safe="")
        return (
            f"postgresql+psycopg://{user}:{password}@"
            f"{self.settings.azure_postgres_host}:{self.settings.azure_postgres_port}/{db}"
            f"?sslmode={sslmode}&connect_timeout={AZURE_POSTGRES_CONNECT_TIMEOUT_SECONDS}"
        )

    def _is_configured(self, config: TowerSourceConfig) -> bool:
        if config.engine_name == "databricks":
            return bool(self.settings.databricks_host and self.settings.databricks_token)
        if config.id == "cloudapp_postgres":
            return bool(config.url)
        return bool(config.url)

    def _engine_for(self, config: TowerSourceConfig) -> Engine:
        if config.id == "cloudapp_postgres":
            return app_engine
        if not config.url:
            raise ValueError("Source URL is not configured.")
        engine_options: dict[str, Any] = {"pool_pre_ping": True}
        if config.source_type == "cloud_database":
            engine_options["connect_args"] = {"connect_timeout": AZURE_POSTGRES_CONNECT_TIMEOUT_SECONDS}
        return create_engine(config.url, **engine_options)

    def _database_fallback(self, config: TowerSourceConfig) -> dict[str, Any]:
        return {
            "source_id": config.id,
            "database_name": config.database_name or "unknown",
            "owner": config.username,
            "encoding": None,
            "is_template": False,
            "allow_connections": True,
            "size_bytes": None,
            "active_connections": 0,
            "total_connections": 0,
            "is_current": True,
            "is_system": False,
        }

    def _store_metric_snapshot(self, config: TowerSourceConfig, snapshot: dict[str, Any]) -> None:
        if not self.settings.controltower_database_url:
            return
        engine: Engine | None = None
        try:
            engine = create_engine(self.settings.controltower_database_url, pool_pre_ping=True)
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO monitored_sources (
                          source_id,
                          name,
                          source_type,
                          engine,
                          environment,
                          host,
                          port,
                          database_name,
                          username,
                          cloud_provider,
                          telemetry_provider,
                          status,
                          last_seen_at,
                          updated_at
                        )
                        VALUES (
                          :source_id,
                          :name,
                          :source_type,
                          :engine,
                          :environment,
                          :host,
                          :port,
                          :database_name,
                          :username,
                          :cloud_provider,
                          :telemetry_provider,
                          :status,
                          now(),
                          now()
                        )
                        ON CONFLICT (source_id) DO UPDATE SET
                          name = EXCLUDED.name,
                          source_type = EXCLUDED.source_type,
                          engine = EXCLUDED.engine,
                          environment = EXCLUDED.environment,
                          host = EXCLUDED.host,
                          port = EXCLUDED.port,
                          database_name = EXCLUDED.database_name,
                          username = EXCLUDED.username,
                          cloud_provider = EXCLUDED.cloud_provider,
                          telemetry_provider = EXCLUDED.telemetry_provider,
                          status = EXCLUDED.status,
                          last_seen_at = now(),
                          updated_at = now()
                        """
                    ),
                    {
                        "source_id": config.id,
                        "name": config.name,
                        "source_type": config.source_type,
                        "engine": config.engine_name,
                        "environment": config.environment,
                        "host": config.host,
                        "port": config.port,
                        "database_name": config.database_name,
                        "username": config.username,
                        "cloud_provider": config.cloud_provider,
                        "telemetry_provider": config.telemetry_provider,
                        "status": snapshot.get("status") or "unknown",
                    },
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO source_metric_snapshots (
                          source_id,
                          captured_at,
                          status,
                          health_score,
                          latency_ms,
                          active_connections,
                          total_connections,
                          idle_connections,
                          database_size_bytes,
                          tables_count,
                          locks_count,
                          cache_hit_ratio,
                          xact_commit,
                          xact_rollback,
                          deadlocks,
                          error,
                          raw_payload
                        )
                        VALUES (
                          :source_id,
                          CAST(:captured_at AS timestamptz),
                          :status,
                          :health_score,
                          :latency_ms,
                          :active_connections,
                          :total_connections,
                          :idle_connections,
                          :database_size_bytes,
                          :tables_count,
                          :locks_count,
                          :cache_hit_ratio,
                          :xact_commit,
                          :xact_rollback,
                          :deadlocks,
                          :error,
                          CAST(:raw_payload AS jsonb)
                        )
                        """
                    ),
                    {
                        "source_id": config.id,
                        "captured_at": snapshot.get("captured_at") or self._now(),
                        "status": snapshot.get("status"),
                        "health_score": snapshot.get("health_score") or 0,
                        "latency_ms": snapshot.get("latency_ms"),
                        "active_connections": snapshot.get("active_connections"),
                        "total_connections": snapshot.get("total_connections"),
                        "idle_connections": snapshot.get("idle_connections"),
                        "database_size_bytes": snapshot.get("database_size_bytes"),
                        "tables_count": snapshot.get("tables_count"),
                        "locks_count": snapshot.get("locks_count"),
                        "cache_hit_ratio": snapshot.get("cache_hit_ratio"),
                        "xact_commit": snapshot.get("xact_commit"),
                        "xact_rollback": snapshot.get("xact_rollback"),
                        "deadlocks": snapshot.get("deadlocks"),
                        "error": snapshot.get("error"),
                        "raw_payload": json.dumps(snapshot, default=str),
                    },
                )
            engine.dispose()
        except Exception:
            if engine is not None:
                try:
                    engine.dispose()
                except Exception:
                    pass

    def _tables_from_inspector(self, config: TowerSourceConfig, engine: Engine) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        try:
            inspector = inspect(engine)
            for schema in [item for item in inspector.get_schema_names() if item not in SYSTEM_SCHEMAS]:
                for table_name in inspector.get_table_names(schema=schema):
                    output.append(
                        {
                            "source_id": config.id,
                            "schema_name": schema,
                            "table_name": table_name,
                            "estimated_rows": None,
                            "size_bytes": None,
                            "table_type": "table",
                            "last_seen_at": self._now(),
                        }
                    )
        except Exception:
            return []
        return output

    def _databricks_snapshot(self, status: str) -> dict[str, Any]:
        tables_count = len(self._databricks_tables_from_catalog())
        health = 90 if status == "online" else 0
        return {
            "status": status,
            "latency_ms": None,
            "active_connections": None,
            "total_connections": None,
            "idle_connections": None,
            "database_size_bytes": None,
            "tables_count": tables_count,
            "locks_count": None,
            "cache_hit_ratio": None,
            "xact_commit": None,
            "xact_rollback": None,
            "deadlocks": None,
            "health_score": health,
            "captured_at": self._now(),
            "error": None if status == "online" else "Databricks connection is not fully configured.",
        }

    def _databricks_tables_from_catalog(self) -> list[dict[str, Any]]:
        schemas = [
            "banco_demo",
            self.settings.databricks_schema_bronze,
            self.settings.databricks_schema_silver,
            self.settings.databricks_schema_gold,
        ]
        table_names = {
            "banco_demo": ["transacciones_demo", "alertas_movimientos_inusuales", "log_ejecucion_alertas"],
            self.settings.databricks_schema_bronze: ["date_dim", "item", "store", "store_sales"],
            self.settings.databricks_schema_silver: ["quarantine_store_sales", "store_sales_clean"],
            self.settings.databricks_schema_gold: ["sales_by_store", "sales_by_year_category"],
        }
        table_sizes = {
            ("banco_demo", "alertas_movimientos_inusuales"): 40274,
            ("banco_demo", "log_ejecucion_alertas"): 26309,
            ("banco_demo", "transacciones_demo"): 29215,
            (self.settings.databricks_schema_bronze, "date_dim"): 339089,
            (self.settings.databricks_schema_bronze, "item"): 1049224,
            (self.settings.databricks_schema_bronze, "store"): 9432,
            (self.settings.databricks_schema_bronze, "store_sales"): 117838003,
            (self.settings.databricks_schema_silver, "quarantine_store_sales"): 1532608,
            (self.settings.databricks_schema_silver, "store_sales_clean"): 148129006,
            (self.settings.databricks_schema_gold, "sales_by_store"): 2332,
            (self.settings.databricks_schema_gold, "sales_by_year_category"): 3381,
        }
        output: list[dict[str, Any]] = []
        for schema in schemas:
            for table_name in table_names.get(schema, []):
                output.append(
                    {
                        "source_id": "databricks_lakehouse",
                        "schema_name": schema,
                        "table_name": table_name,
                        "estimated_rows": None,
                        "size_bytes": table_sizes.get((schema, table_name)),
                        "table_type": "delta",
                        "last_seen_at": self._now(),
                    }
                )
        return output

    def _databricks_tables_from_db(self, db: Session) -> list[dict[str, Any]]:
        assets = db.query(CatalogAsset).filter(CatalogAsset.platform == "databricks").order_by(CatalogAsset.schema_name, CatalogAsset.table_name).all()
        if not assets:
            return self._databricks_tables_from_catalog()
        return [
            {
                "source_id": "databricks_lakehouse",
                "schema_name": asset.schema_name or "default",
                "table_name": asset.table_name or asset.asset_name,
                "estimated_rows": asset.row_count,
                "size_bytes": asset.total_size_bytes,
                "table_type": "delta",
                "last_seen_at": asset.updated_at.isoformat() if asset.updated_at else self._now(),
            }
            for asset in assets
        ]

    def _try_databricks_live_tables(self) -> list[dict[str, Any]]:
        if not (self.settings.databricks_host and self.settings.databricks_token and self.settings.databricks_sql_warehouse_id):
            return []
        # Keep the MVP read-only and small: one SHOW TABLES per configured schema.
        output: list[dict[str, Any]] = []
        for schema in {
            "banco_demo",
            self.settings.databricks_schema_bronze,
            self.settings.databricks_schema_silver,
            self.settings.databricks_schema_gold,
        }:
            statement = f"SHOW TABLES IN {self.settings.databricks_catalog}.{schema}"
            rows = self._execute_databricks_statement(statement)
            for row in rows:
                table_name = row.get("tableName") or row.get("table_name") or row.get("tablename")
                if table_name:
                    detail = self._databricks_table_detail(schema, str(table_name))
                    output.append(
                        {
                            "source_id": "databricks_lakehouse",
                            "schema_name": schema,
                            "table_name": str(table_name),
                            "estimated_rows": _first_int(detail, ["numRows", "rowCount", "estimatedRows"]),
                            "size_bytes": _first_int(detail, ["sizeInBytes", "size_bytes"]),
                            "table_type": str(detail.get("format") or "delta").lower(),
                            "last_seen_at": self._now(),
                        }
                    )
        return output

    def _databricks_table_detail(self, schema: str, table_name: str) -> dict[str, Any]:
        full_name = ".".join(
            [
                _quote_databricks_identifier(self.settings.databricks_catalog),
                _quote_databricks_identifier(schema),
                _quote_databricks_identifier(table_name),
            ]
        )
        rows = self._execute_databricks_statement(f"DESCRIBE DETAIL {full_name}")
        return rows[0] if rows else {}

    def _execute_databricks_statement(self, statement: str) -> list[dict[str, Any]]:
        host = str(self.settings.databricks_host).rstrip("/")
        headers = {"Authorization": f"Bearer {self.settings.databricks_token}", "Content-Type": "application/json"}
        payload = {
            "warehouse_id": self.settings.databricks_sql_warehouse_id,
            "statement": statement,
            "wait_timeout": "10s",
            "disposition": "INLINE",
        }
        try:
            response = httpx.post(f"{host}/api/2.0/sql/statements", headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            data = response.json()
            rows = _databricks_rows_from_response(data)
            if rows:
                return rows

            statement_id = data.get("statement_id") or data.get("statementId")
            if not statement_id:
                return []

            for _ in range(18):
                state = str((data.get("status") or {}).get("state") or "").upper()
                if state in {"FAILED", "CANCELED", "CANCELLED", "CLOSED"}:
                    return []
                if state == "SUCCEEDED":
                    return _databricks_rows_from_response(data)
                sleep(2)
                poll = httpx.get(f"{host}/api/2.0/sql/statements/{statement_id}", headers=headers, timeout=15)
                poll.raise_for_status()
                data = poll.json()
                rows = _databricks_rows_from_response(data)
                if rows:
                    return rows
            return []
        except Exception as exc:
            logger.warning("Databricks statement failed: %s", exc)
            return []

    def _health_score(self, snapshot: dict[str, Any], config: TowerSourceConfig) -> int:
        score = 100
        latency = snapshot.get("latency_ms") or 0
        if latency > 250:
            score -= 25
        elif latency > 100:
            score -= 10
        total_connections = snapshot.get("total_connections") or 0
        active_connections = snapshot.get("active_connections") or 0
        locks_count = snapshot.get("locks_count") or 0
        if total_connections > 100:
            score -= 15
        elif total_connections > 50:
            score -= 8
        if active_connections > 50:
            score -= 10
        if locks_count > 50:
            score -= 18
        elif locks_count > 0:
            score -= 5
        if snapshot.get("deadlocks"):
            score -= 5
        if config.source_type == "cloud_database" and not self.settings.azure_postgres_resource_id:
            score -= 3
        return max(0, min(100, int(score)))

    def _recommendation(
        self,
        source: dict[str, Any],
        severity: str,
        category: str,
        title: str,
        recommendation: str,
        evidence: str,
        impact: str,
        action_type: str,
    ) -> dict[str, Any]:
        return {
            "id": f"rec-{source['id']}-{category.lower().replace(' ', '-')}",
            "source_id": source["id"],
            "severity": severity,
            "category": category,
            "title": title,
            "recommendation": recommendation,
            "evidence": evidence,
            "impact": impact,
            "action_type": action_type,
        }

    def _empty_snapshot(self, status: str, health_score: int, error: str | None, latency_ms: float | None = None) -> dict[str, Any]:
        return {
            "status": status,
            "latency_ms": latency_ms,
            "active_connections": None,
            "total_connections": None,
            "idle_connections": None,
            "database_size_bytes": None,
            "tables_count": None,
            "locks_count": None,
            "cache_hit_ratio": None,
            "xact_commit": None,
            "xact_rollback": None,
            "deadlocks": None,
            "health_score": health_score,
            "captured_at": self._now(),
            "error": error,
        }

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def _json_safe_dict(row: Any) -> dict[str, Any]:
    return {key: _json_safe(value) for key, value in dict(row).items()}


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _port_from_url(url: str | None, fallback: int) -> int | None:
    if not url:
        return fallback
    parsed = urlparse(_normalized_url(url))
    return parsed.port or fallback


def _username_from_url(url: str | None) -> str | None:
    if not url:
        return None
    return urlparse(_normalized_url(url)).username


def _has_percent_escape(value: str) -> bool:
    for index in range(len(value) - 2):
        if value[index] != "%":
            continue
        if all(char in "0123456789abcdefABCDEF" for char in value[index + 1 : index + 3]):
            return True
    return False


def _first_int(row: dict[str, Any], keys: list[str]) -> int | None:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return None


def _databricks_rows_from_response(data: dict[str, Any]) -> list[dict[str, Any]]:
    columns = [column.get("name") for column in data.get("manifest", {}).get("schema", {}).get("columns", [])]
    rows = data.get("result", {}).get("data_array", [])
    return [dict(zip(columns, row, strict=False)) for row in rows if columns]


def _quote_databricks_identifier(value: str | None) -> str:
    cleaned = str(value or "").replace("`", "``")
    return f"`{cleaned}`"


def _normalized_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)
