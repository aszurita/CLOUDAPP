"""
Recolecta telemetría de PostgreSQL desde pg_stat_* cada N segundos.
Almacena en tablas sentinel_* de la base de datos operacional (CLOUDAPP).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# ── SQL queries ────────────────────────────────────────────────────────────────

SQL_ACTIVITY = """
SELECT
    COUNT(*) AS total_sessions,
    COUNT(*) FILTER (WHERE state = 'active') AS active_sessions,
    COUNT(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction,
    COUNT(*) FILTER (WHERE wait_event_type IS NOT NULL) AS waiting_sessions,
    COUNT(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting_sessions,
    COUNT(*) FILTER (WHERE wait_event = 'WALWriteLock') AS wal_write_lock_sessions
FROM pg_stat_activity
WHERE pid != pg_backend_pid()
"""

SQL_LOCKS = """
SELECT
    COUNT(*) FILTER (WHERE granted) AS locks_granted,
    COUNT(*) FILTER (WHERE NOT granted) AS locks_waiting,
    COUNT(DISTINCT pid) FILTER (WHERE NOT granted) AS pids_waiting
FROM pg_locks
WHERE pid != pg_backend_pid()
"""

SQL_DATABASE = """
SELECT
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    ROUND(
        blks_hit::numeric / NULLIF(blks_hit + blks_read, 0) * 100, 4
    ) AS cache_hit_ratio,
    deadlocks,
    temp_files,
    temp_bytes,
    blk_read_time,
    blk_write_time
FROM pg_stat_database
WHERE datname = current_database()
"""

SQL_WAL = """
SELECT
    wal_records,
    wal_bytes,
    wal_buffers_full,
    wal_write_time,
    wal_sync_time
FROM pg_stat_wal
"""

SQL_STATEMENTS = """
SELECT
    queryid,
    LEFT(query, 300) AS query_preview,
    calls,
    total_exec_time,
    mean_exec_time,
    stddev_exec_time,
    rows,
    shared_blks_hit,
    shared_blks_read,
    temp_blks_read,
    wal_bytes
FROM pg_stat_statements
WHERE query NOT LIKE '%pg_stat%'
ORDER BY mean_exec_time DESC
LIMIT 30
"""

SQL_REPLICATION = """
SELECT
    COALESCE(MAX(EXTRACT(EPOCH FROM replay_lag)), 0) AS max_replay_lag_seconds,
    COALESCE(MAX(EXTRACT(EPOCH FROM write_lag)), 0) AS max_write_lag_seconds,
    COUNT(*) AS replica_count
FROM pg_stat_replication
"""

SQL_LONG_TRANSACTIONS = """
SELECT COUNT(*) AS long_transactions_count
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
  AND EXTRACT(EPOCH FROM (NOW() - xact_start)) > 30
  AND pid != pg_backend_pid()
"""


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
        self._previous_db_stats: Optional[dict] = None
        self._previous_query_stats: Optional[dict] = None
        self._running = False

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
        monitor_conn = await asyncpg.connect(**self._conn_kwargs(self.monitor_dsn))
        storage_conn = await asyncpg.connect(**self._conn_kwargs(self.storage_dsn))

        try:
            collected_at = datetime.now(timezone.utc)

            # Secuenciales: asyncpg no soporta queries paralelas en la misma conexión
            activity   = await monitor_conn.fetchrow(SQL_ACTIVITY)
            locks      = await monitor_conn.fetchrow(SQL_LOCKS)
            db_stats   = await monitor_conn.fetchrow(SQL_DATABASE)
            wal_stats  = await monitor_conn.fetchrow(SQL_WAL)
            stmts      = await monitor_conn.fetch(SQL_STATEMENTS)
            replication = await monitor_conn.fetchrow(SQL_REPLICATION)
            long_txn   = await monitor_conn.fetchrow(SQL_LONG_TRANSACTIONS)

            # Calcular deltas para contadores acumulados
            xact_commit_delta = xact_rollback_delta = deadlocks_delta = 0
            wal_bytes_delta = wal_buffers_full_delta = 0

            if self._previous_db_stats:
                prev = self._previous_db_stats
                xact_commit_delta = max(0, db_stats["xact_commit"] - prev.get("xact_commit", 0))
                xact_rollback_delta = max(0, db_stats["xact_rollback"] - prev.get("xact_rollback", 0))
                deadlocks_delta = max(0, db_stats["deadlocks"] - prev.get("deadlocks", 0))
                wal_bytes_delta = max(0, (wal_stats["wal_bytes"] or 0) - prev.get("wal_bytes", 0))
                wal_buffers_full_delta = max(0, (wal_stats["wal_buffers_full"] or 0) - prev.get("wal_buffers_full", 0))

            self._previous_db_stats = {
                "xact_commit": db_stats["xact_commit"],
                "xact_rollback": db_stats["xact_rollback"],
                "deadlocks": db_stats["deadlocks"],
                "wal_bytes": wal_stats["wal_bytes"] or 0,
                "wal_buffers_full": wal_stats["wal_buffers_full"] or 0,
            }

            raw_payload = {
                "activity": dict(activity),
                "locks": dict(locks),
                "database": dict(db_stats),
                "wal": dict(wal_stats),
                "replication": dict(replication),
            }

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
                collected_at, "postgresql", self.database_name,
                activity["active_sessions"],
                activity["waiting_sessions"],
                activity["idle_in_transaction"],
                activity["lock_waiting_sessions"],
                locks["locks_granted"],
                locks["locks_waiting"],
                long_txn["long_transactions_count"],
                xact_commit_delta,
                xact_rollback_delta,
                float(db_stats["cache_hit_ratio"] or 0),
                deadlocks_delta,
                db_stats["temp_files"] or 0,
                db_stats["temp_bytes"] or 0,
                float(db_stats["blk_read_time"] or 0),
                wal_bytes_delta,
                wal_buffers_full_delta,
                float(replication["max_replay_lag_seconds"] or 0),
                replication["replica_count"],
                json.dumps(raw_payload, default=str),
            )

            # Insertar muestras de queries con deltas
            for stmt in stmts:
                prev_q = (self._previous_query_stats or {}).get(stmt["queryid"], {})
                await storage_conn.execute(
                    """
                    INSERT INTO sentinel_query_samples (
                        collected_at, queryid, query_fingerprint,
                        calls_delta, mean_exec_time, stddev_exec_time,
                        rows_delta, wal_bytes_delta
                    ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    collected_at,
                    stmt["queryid"],
                    stmt["query_preview"],
                    max(0, stmt["calls"] - prev_q.get("calls", 0)),
                    float(stmt["mean_exec_time"] or 0),
                    float(stmt["stddev_exec_time"] or 0),
                    max(0, stmt["rows"] - prev_q.get("rows", 0)),
                    max(0, (stmt["wal_bytes"] or 0) - prev_q.get("wal_bytes", 0)),
                )

            self._previous_query_stats = {
                stmt["queryid"]: {
                    "calls": stmt["calls"],
                    "rows": stmt["rows"],
                    "wal_bytes": stmt["wal_bytes"] or 0,
                }
                for stmt in stmts
            }

            result = {
                "collected_at": collected_at.isoformat(),
                "active_sessions": activity["active_sessions"],
                "lock_waiting_sessions": activity["lock_waiting_sessions"],
                "cache_hit_ratio": float(db_stats["cache_hit_ratio"] or 0),
                "wal_bytes_delta": wal_bytes_delta,
                "replication_lag_seconds": float(replication["max_replay_lag_seconds"] or 0),
            }
            logger.info(
                "Telemetría recolectada — db=%s active=%s lock_waiting=%s cache=%.2f%%",
                self.database_name,
                activity["active_sessions"],
                activity["lock_waiting_sessions"],
                float(db_stats["cache_hit_ratio"] or 0),
            )
            return result

        finally:
            await monitor_conn.close()
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
