"""PostgreSQL telemetry adapter for DB Sentinel AI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

import asyncpg

from app.services.sentinel.adapters.base_adapter import BaseDBAdapter, CanonicalMetrics, QuerySample

logger = logging.getLogger(__name__)

SQL_ACTIVITY = """
SELECT
    COUNT(*) FILTER (WHERE state = 'active') AS active_sessions,
    COUNT(*) FILTER (WHERE state = 'idle in transaction') AS idle_in_transaction,
    COUNT(*) FILTER (WHERE wait_event_type IS NOT NULL) AS waiting_sessions,
    COUNT(*) FILTER (WHERE wait_event_type = 'Lock') AS lock_waiting_sessions
FROM pg_stat_activity
WHERE pid != pg_backend_pid()
"""

SQL_LOCKS = """
SELECT
    COUNT(*) FILTER (WHERE granted) AS locks_granted,
    COUNT(*) FILTER (WHERE NOT granted) AS locks_waiting
FROM pg_locks
WHERE pid != pg_backend_pid()
"""

SQL_DATABASE = """
SELECT
    xact_commit,
    xact_rollback,
    blks_read,
    blks_hit,
    ROUND(blks_hit::numeric / NULLIF(blks_hit + blks_read, 0) * 100, 4) AS cache_hit_ratio,
    deadlocks,
    temp_files,
    temp_bytes,
    blk_read_time
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
    mean_exec_time,
    stddev_exec_time,
    rows,
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


class PostgresAdapter(BaseDBAdapter):
    ENGINE = "postgresql"

    @staticmethod
    def conn_kwargs(dsn: str) -> dict[str, Any]:
        parsed = urlparse(dsn)
        is_local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        return {
            "host": parsed.hostname,
            "port": parsed.port or 5432,
            "user": parsed.username,
            "password": unquote(parsed.password or ""),
            "database": parsed.path.lstrip("/"),
            "ssl": False if is_local else True,
        }

    async def test_connection(self) -> bool:
        try:
            conn = await asyncpg.connect(**self.conn_kwargs(self.connection_string))
            try:
                await conn.fetchval("SELECT 1")
            finally:
                await conn.close()
            return True
        except Exception:
            logger.exception("PostgreSQL adapter connection test failed")
            return False

    async def collect(self) -> CanonicalMetrics:
        conn = await asyncpg.connect(**self.conn_kwargs(self.connection_string))
        try:
            collected_at = datetime.now(timezone.utc)
            activity = await conn.fetchrow(SQL_ACTIVITY)
            locks = await conn.fetchrow(SQL_LOCKS)
            db_stats = await conn.fetchrow(SQL_DATABASE)
            wal_stats = await conn.fetchrow(SQL_WAL)
            replication = await conn.fetchrow(SQL_REPLICATION)
            long_txn = await conn.fetchrow(SQL_LONG_TRANSACTIONS)
            statements = await self._safe_fetch_statements(conn)

            query_samples = [
                QuerySample(
                    queryid=stmt["queryid"],
                    query_fingerprint=stmt["query_preview"] or "",
                    calls_delta=self._delta(f"query_calls:{stmt['queryid']}", stmt["calls"]),
                    mean_exec_time=float(stmt["mean_exec_time"] or 0),
                    stddev_exec_time=float(stmt["stddev_exec_time"] or 0),
                    rows_delta=self._delta(f"query_rows:{stmt['queryid']}", stmt["rows"]),
                    wal_bytes_delta=self._delta(f"query_wal:{stmt['queryid']}", stmt["wal_bytes"] or 0),
                )
                for stmt in statements
            ]
            mean_query_latency = (
                sum(sample.mean_exec_time for sample in query_samples[:10]) / min(len(query_samples), 10)
                if query_samples
                else 0.0
            )

            raw = {
                "activity": dict(activity or {}),
                "locks": dict(locks or {}),
                "database": dict(db_stats or {}),
                "wal": dict(wal_stats or {}),
                "replication": dict(replication or {}),
            }
            return CanonicalMetrics(
                collected_at=collected_at,
                engine=self.ENGINE,
                database_name=self.database_name,
                active_sessions=int((activity or {}).get("active_sessions") or 0),
                waiting_sessions=int((activity or {}).get("waiting_sessions") or 0),
                lock_waiting_sessions=int((activity or {}).get("lock_waiting_sessions") or 0),
                idle_in_transaction=int((activity or {}).get("idle_in_transaction") or 0),
                locks_granted=int((locks or {}).get("locks_granted") or 0),
                locks_waiting=int((locks or {}).get("locks_waiting") or 0),
                long_transactions_count=int((long_txn or {}).get("long_transactions_count") or 0),
                xact_commit_delta=self._delta("xact_commit", (db_stats or {}).get("xact_commit")),
                xact_rollback_delta=self._delta("xact_rollback", (db_stats or {}).get("xact_rollback")),
                deadlocks_delta=self._delta("deadlocks", (db_stats or {}).get("deadlocks")),
                cache_hit_ratio=float((db_stats or {}).get("cache_hit_ratio") or 0),
                wal_bytes_delta=self._delta("wal_bytes", (wal_stats or {}).get("wal_bytes")),
                wal_buffers_full_delta=self._delta("wal_buffers_full", (wal_stats or {}).get("wal_buffers_full")),
                blk_read_time_delta=float((db_stats or {}).get("blk_read_time") or 0),
                temp_files_delta=int((db_stats or {}).get("temp_files") or 0),
                temp_bytes_delta=int((db_stats or {}).get("temp_bytes") or 0),
                replication_lag_seconds=float((replication or {}).get("max_replay_lag_seconds") or 0),
                replica_count=int((replication or {}).get("replica_count") or 0),
                mean_query_latency_ms=mean_query_latency,
                query_samples=query_samples,
                raw=raw,
            )
        finally:
            await conn.close()

    @staticmethod
    async def _safe_fetch_statements(conn: asyncpg.Connection) -> list[asyncpg.Record]:
        try:
            return list(await conn.fetch(SQL_STATEMENTS))
        except Exception:
            logger.warning("pg_stat_statements unavailable; continuing without query samples", exc_info=True)
            return []
