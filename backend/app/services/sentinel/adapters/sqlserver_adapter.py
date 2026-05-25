"""SQL Server telemetry adapter for DB Sentinel AI.

The adapter is beta and dependency-optional. It can be instantiated without
`aioodbc`; connection and collection report a clear unavailable state.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

try:
    import aioodbc  # type: ignore
except ImportError:  # pragma: no cover - exercised when dependency is absent
    aioodbc = None

from app.services.sentinel.adapters.base_adapter import BaseDBAdapter, CanonicalMetrics, QuerySample

logger = logging.getLogger(__name__)

SQLSERVER_ACTIVITY = """
SELECT
    SUM(CASE WHEN s.status = 'running' THEN 1 ELSE 0 END) AS active_sessions,
    SUM(CASE WHEN r.wait_type IS NOT NULL AND r.wait_type <> '' THEN 1 ELSE 0 END) AS waiting_sessions,
    SUM(CASE WHEN r.wait_type LIKE 'LCK%' THEN 1 ELSE 0 END) AS lock_waiting_sessions,
    SUM(CASE WHEN s.status = 'sleeping' AND s.open_transaction_count > 0 THEN 1 ELSE 0 END) AS idle_in_transaction,
    SUM(CASE WHEN s.open_transaction_count > 0 THEN 1 ELSE 0 END) AS long_transactions_count
FROM sys.dm_exec_sessions s
LEFT JOIN sys.dm_exec_requests r ON s.session_id = r.session_id
WHERE s.is_user_process = 1
"""

SQLSERVER_LOCKS = """
SELECT
    SUM(CASE WHEN request_status = 'GRANT' THEN 1 ELSE 0 END) AS locks_granted,
    SUM(CASE WHEN request_status <> 'GRANT' THEN 1 ELSE 0 END) AS locks_waiting
FROM sys.dm_tran_locks
"""

SQLSERVER_COUNTERS = """
SELECT counter_name, instance_name, cntr_value
FROM sys.dm_os_performance_counters
WHERE counter_name IN (
    'Buffer cache hit ratio',
    'Transactions/sec',
    'Log Bytes Flushed/sec',
    'Log Flush Waits/sec',
    'Number of Deadlocks/sec'
)
"""

SQLSERVER_QUERY_STATS = """
SELECT TOP 30
    CONVERT(varchar(64), qs.query_hash, 1) AS queryid,
    LEFT(qt.text, 300) AS query_preview,
    qs.execution_count AS calls,
    CASE WHEN qs.execution_count > 0 THEN qs.total_elapsed_time / qs.execution_count / 1000.0 ELSE 0 END AS mean_exec_time,
    qs.total_rows AS rows
FROM sys.dm_exec_query_stats qs
CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) qt
WHERE qs.execution_count > 0
ORDER BY mean_exec_time DESC
"""


class SQLServerAdapter(BaseDBAdapter):
    ENGINE = "sqlserver"

    async def test_connection(self) -> bool:
        if aioodbc is None:
            logger.info("aioodbc is not installed; SQL Server adapter unavailable")
            return False
        try:
            async with aioodbc.connect(dsn=self.connection_string) as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    await cursor.fetchone()
            return True
        except Exception:
            logger.exception("SQL Server adapter connection test failed")
            return False

    async def collect(self) -> CanonicalMetrics:
        if aioodbc is None:
            raise RuntimeError("SQL Server adapter requires optional dependency aioodbc")

        async with aioodbc.connect(dsn=self.connection_string) as conn:
            activity = await self._fetch_one(conn, SQLSERVER_ACTIVITY)
            locks = await self._fetch_one(conn, SQLSERVER_LOCKS)
            counters = await self._fetch_all(conn, SQLSERVER_COUNTERS)
            statements = await self._fetch_all(conn, SQLSERVER_QUERY_STATS)

        counter_map = {row["counter_name"]: int(row["cntr_value"] or 0) for row in counters}
        query_samples = [
            QuerySample(
                queryid=row.get("queryid"),
                query_fingerprint=str(row.get("query_preview") or ""),
                calls_delta=self._delta(f"query_calls:{row.get('queryid')}", row.get("calls")),
                mean_exec_time=float(row.get("mean_exec_time") or 0),
                rows_delta=self._delta(f"query_rows:{row.get('queryid')}", row.get("rows")),
            )
            for row in statements
        ]
        return CanonicalMetrics(
            collected_at=datetime.now(timezone.utc),
            engine=self.ENGINE,
            database_name=self.database_name,
            active_sessions=int(activity.get("active_sessions") or 0),
            waiting_sessions=int(activity.get("waiting_sessions") or 0),
            lock_waiting_sessions=int(activity.get("lock_waiting_sessions") or 0),
            idle_in_transaction=int(activity.get("idle_in_transaction") or 0),
            long_transactions_count=int(activity.get("long_transactions_count") or 0),
            locks_granted=int(locks.get("locks_granted") or 0),
            locks_waiting=int(locks.get("locks_waiting") or 0),
            cache_hit_ratio=float(counter_map.get("Buffer cache hit ratio", 0)),
            xact_commit_delta=self._delta("transactions", counter_map.get("Transactions/sec", 0)),
            deadlocks_delta=self._delta("deadlocks", counter_map.get("Number of Deadlocks/sec", 0)),
            wal_bytes_delta=self._delta("log_bytes", counter_map.get("Log Bytes Flushed/sec", 0)),
            wal_buffers_full_delta=self._delta("log_flush_waits", counter_map.get("Log Flush Waits/sec", 0)),
            mean_query_latency_ms=sum(q.mean_exec_time for q in query_samples[:10]) / min(len(query_samples), 10)
            if query_samples
            else 0.0,
            query_samples=query_samples,
            raw={"activity": activity, "locks": locks, "counters": counters},
        )

    @staticmethod
    async def _fetch_one(conn: Any, sql: str) -> dict[str, Any]:
        async with conn.cursor() as cursor:
            await cursor.execute(sql)
            row = await cursor.fetchone()
            if row is None:
                return {}
            return dict(zip([col[0] for col in cursor.description], row))

    @staticmethod
    async def _fetch_all(conn: Any, sql: str) -> list[dict[str, Any]]:
        async with conn.cursor() as cursor:
            await cursor.execute(sql)
            rows = await cursor.fetchall()
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
