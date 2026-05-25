"""
Recolecta telemetría de PostgreSQL desde pg_stat_* cada N segundos.
Almacena en tablas sentinel_* de la base de datos operacional (CLOUDAPP).
"""
from __future__ import annotations

import asyncio
import json
import logging

import asyncpg

from app.services.sentinel.adapters.postgres_adapter import PostgresAdapter

logger = logging.getLogger(__name__)


class PostgresCollector:
    """Recolecta telemetría de una instancia PostgreSQL y la persiste."""

    def __init__(
        self,
        monitor_dsn: str,
        storage_dsn: str,
        interval_seconds: int = 60,
        database_name: str = "unknown",
    ):
        self.monitor_dsn = monitor_dsn
        self.storage_dsn = storage_dsn
        self.interval = interval_seconds
        self.database_name = database_name
        self._running = False
        self.adapter = PostgresAdapter(
            connection_string=monitor_dsn,
            database_name=database_name,
        )

    @staticmethod
    def _conn_kwargs(dsn: str) -> dict:
        """Parsea el DSN y devuelve kwargs para asyncpg.connect() con ssl correcto."""
        from urllib.parse import urlparse, unquote
        p = urlparse(dsn)
        is_local = p.hostname in ("localhost", "127.0.0.1")
        return dict(
            host=p.hostname,
            port=p.port or 5432,
            user=p.username,
            password=unquote(p.password or ""),
            database=p.path.lstrip("/"),
            ssl=False if is_local else True,
        )

    async def collect_once(self) -> dict:
        """Recolecta una muestra completa de telemetría y la persiste."""
        storage_conn = await asyncpg.connect(**self._conn_kwargs(self.storage_dsn))

        try:
            metrics = await self.adapter.collect()
            await storage_conn.execute(
                """
                INSERT INTO sentinel_metric_samples (
                    collected_at, engine, database_name,
                    active_sessions, waiting_sessions, idle_in_transaction,
                    lock_waiting_sessions, locks_granted, locks_waiting,
                    long_transactions_count, xact_commit_delta, xact_rollback_delta,
                    cache_hit_ratio, deadlocks_delta, temp_files_delta, temp_bytes_delta,
                    blk_read_time_delta, wal_bytes_delta, wal_buffers_full_delta,
                    replication_lag_seconds, replica_count, raw_json
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22
                )
                """,
                *metrics.storage_metric_values(),
                json.dumps(metrics.raw, default=str),
            )

            for sample in metrics.query_samples:
                await storage_conn.execute(
                    """
                    INSERT INTO sentinel_query_samples (
                        collected_at, queryid, query_fingerprint,
                        calls_delta, mean_exec_time, stddev_exec_time,
                        rows_delta, wal_bytes_delta
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    metrics.collected_at,
                    sample.queryid if isinstance(sample.queryid, int) else None,
                    sample.query_fingerprint,
                    sample.calls_delta,
                    sample.mean_exec_time,
                    sample.stddev_exec_time,
                    sample.rows_delta,
                    sample.wal_bytes_delta,
                )

            result = {
                "collected_at": metrics.collected_at.isoformat(),
                "engine": metrics.engine,
                "database_name": metrics.database_name,
                "active_sessions": metrics.active_sessions,
                "lock_waiting_sessions": metrics.lock_waiting_sessions,
                "cache_hit_ratio": metrics.cache_hit_ratio,
                "wal_bytes_delta": metrics.wal_bytes_delta,
                "replication_lag_seconds": metrics.replication_lag_seconds,
            }
            logger.info(
                "Telemetría recolectada — db=%s active=%s lock_waiting=%s cache=%.2f%%",
                self.database_name,
                metrics.active_sessions,
                metrics.lock_waiting_sessions,
                metrics.cache_hit_ratio,
            )
            return result

        finally:
            await storage_conn.close()

    async def run_continuous(self) -> None:
        """Loop de recolección continua hasta que se llame stop()."""
        self._running = True
        logger.info("Collector iniciado — db=%s intervalo=%ss", self.database_name, self.interval)
        while self._running:
            try:
                await self.collect_once()
            except Exception:
                logger.exception("Error en ciclo de recolección")
            await asyncio.sleep(self.interval)

    def stop(self) -> None:
        self._running = False
