"""MySQL/MariaDB telemetry adapter for DB Sentinel AI."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

try:
    import aiomysql  # type: ignore
except ImportError:  # pragma: no cover - exercised when dependency is absent
    aiomysql = None

from app.services.sentinel.adapters.base_adapter import BaseDBAdapter, CanonicalMetrics, QuerySample

logger = logging.getLogger(__name__)

MYSQL_ACTIVITY = """
SELECT
    COUNT(CASE WHEN COMMAND <> 'Sleep' THEN 1 END) AS active_sessions,
    COUNT(CASE WHEN STATE IS NOT NULL AND STATE <> '' THEN 1 END) AS waiting_sessions,
    COUNT(CASE WHEN COMMAND = 'Sleep' AND TIME > 30 THEN 1 END) AS idle_in_transaction
FROM information_schema.processlist
WHERE USER <> 'system user'
"""

MYSQL_LOCK_WAITS = """
SELECT COUNT(DISTINCT REQUESTING_ENGINE_TRANSACTION_ID) AS lock_waiting_sessions
FROM performance_schema.data_lock_waits
"""

MYSQL_STATUS = """
SELECT VARIABLE_NAME, VARIABLE_VALUE
FROM performance_schema.global_status
WHERE VARIABLE_NAME IN (
    'Innodb_buffer_pool_reads',
    'Innodb_buffer_pool_read_requests',
    'Innodb_deadlocks',
    'Innodb_os_log_written',
    'Innodb_log_waits',
    'Com_commit',
    'Com_rollback',
    'Created_tmp_disk_tables',
    'Innodb_data_read'
)
"""

MYSQL_QUERY_STATS = """
SELECT
    DIGEST AS queryid,
    LEFT(DIGEST_TEXT, 300) AS query_preview,
    COUNT_STAR AS calls,
    AVG_TIMER_WAIT / 1000000000.0 AS mean_exec_time,
    SUM_ROWS_SENT AS rows,
    SUM_NO_INDEX_USED AS no_index_used
FROM performance_schema.events_statements_summary_by_digest
WHERE SCHEMA_NAME = DATABASE()
ORDER BY AVG_TIMER_WAIT DESC
LIMIT 30
"""


class MySQLAdapter(BaseDBAdapter):
    ENGINE = "mysql"

    @staticmethod
    def conn_kwargs(connection_string: str, database_name: str) -> dict[str, Any]:
        parsed = urlparse(connection_string)
        return {
            "host": parsed.hostname or "localhost",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "db": parsed.path.lstrip("/") or database_name,
            "autocommit": True,
        }

    async def test_connection(self) -> bool:
        if aiomysql is None:
            logger.info("aiomysql is not installed; MySQL adapter unavailable")
            return False
        try:
            conn = await aiomysql.connect(**self.conn_kwargs(self.connection_string, self.database_name))
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("SELECT 1")
                    await cursor.fetchone()
            finally:
                conn.close()
            return True
        except Exception:
            logger.exception("MySQL adapter connection test failed")
            return False

    async def collect(self) -> CanonicalMetrics:
        if aiomysql is None:
            raise RuntimeError("MySQL adapter requires optional dependency aiomysql")

        conn = await aiomysql.connect(**self.conn_kwargs(self.connection_string, self.database_name))
        try:
            activity = await self._fetch_one(conn, MYSQL_ACTIVITY)
            lock_waits = await self._safe_fetch_one(conn, MYSQL_LOCK_WAITS)
            status_rows = await self._fetch_all(conn, MYSQL_STATUS)
            statements = await self._safe_fetch_all(conn, MYSQL_QUERY_STATS)
        finally:
            conn.close()

        status = {row["VARIABLE_NAME"]: int(row["VARIABLE_VALUE"] or 0) for row in status_rows}
        reads = status.get("Innodb_buffer_pool_reads", 0)
        requests = status.get("Innodb_buffer_pool_read_requests", 0)
        cache_hit_ratio = (requests / (requests + reads) * 100) if (requests + reads) else 0.0
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
            lock_waiting_sessions=int(lock_waits.get("lock_waiting_sessions") or 0),
            idle_in_transaction=int(activity.get("idle_in_transaction") or 0),
            cache_hit_ratio=cache_hit_ratio,
            xact_commit_delta=self._delta("com_commit", status.get("Com_commit", 0)),
            xact_rollback_delta=self._delta("com_rollback", status.get("Com_rollback", 0)),
            deadlocks_delta=self._delta("deadlocks", status.get("Innodb_deadlocks", 0)),
            wal_bytes_delta=self._delta("redo_bytes", status.get("Innodb_os_log_written", 0)),
            wal_buffers_full_delta=self._delta("redo_waits", status.get("Innodb_log_waits", 0)),
            temp_files_delta=self._delta("tmp_disk_tables", status.get("Created_tmp_disk_tables", 0)),
            blk_read_time_delta=float(self._delta("data_read", status.get("Innodb_data_read", 0))),
            mean_query_latency_ms=sum(q.mean_exec_time for q in query_samples[:10]) / min(len(query_samples), 10)
            if query_samples
            else 0.0,
            query_samples=query_samples,
            raw={"activity": activity, "lock_waits": lock_waits, "status": status},
        )

    @staticmethod
    async def _fetch_one(conn: Any, sql: str) -> dict[str, Any]:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql)
            return await cursor.fetchone() or {}

    @staticmethod
    async def _fetch_all(conn: Any, sql: str) -> list[dict[str, Any]]:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(sql)
            return list(await cursor.fetchall())

    @classmethod
    async def _safe_fetch_one(cls, conn: Any, sql: str) -> dict[str, Any]:
        try:
            return await cls._fetch_one(conn, sql)
        except Exception:
            logger.warning("Optional MySQL telemetry query failed", exc_info=True)
            return {}

    @classmethod
    async def _safe_fetch_all(cls, conn: Any, sql: str) -> list[dict[str, Any]]:
        try:
            return await cls._fetch_all(conn, sql)
        except Exception:
            logger.warning("Optional MySQL query stats unavailable", exc_info=True)
            return []
