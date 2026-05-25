"""Canonical database telemetry contract for DB Sentinel AI."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class QuerySample:
    queryid: int | str | None
    query_fingerprint: str
    calls_delta: int = 0
    mean_exec_time: float = 0.0
    stddev_exec_time: float = 0.0
    rows_delta: int = 0
    wal_bytes_delta: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CanonicalMetrics:
    """Engine-agnostic telemetry consumed by the feature builder and ML models."""

    collected_at: datetime
    engine: str
    database_name: str

    active_sessions: int = 0
    waiting_sessions: int = 0
    lock_waiting_sessions: int = 0
    idle_in_transaction: int = 0
    locks_granted: int = 0
    locks_waiting: int = 0
    long_transactions_count: int = 0

    xact_commit_delta: int = 0
    xact_rollback_delta: int = 0
    deadlocks_delta: int = 0
    cache_hit_ratio: float = 0.0
    wal_bytes_delta: int = 0
    wal_buffers_full_delta: int = 0
    blk_read_time_delta: float = 0.0
    temp_files_delta: int = 0
    temp_bytes_delta: int = 0
    replication_lag_seconds: float = 0.0
    replica_count: int = 0

    mean_query_latency_ms: float = 0.0
    query_samples: list[QuerySample] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["collected_at"] = self.collected_at.isoformat()
        return payload

    def storage_metric_values(self) -> tuple[Any, ...]:
        return (
            self.collected_at,
            self.engine,
            self.database_name,
            self.active_sessions,
            self.waiting_sessions,
            self.idle_in_transaction,
            self.lock_waiting_sessions,
            self.locks_granted,
            self.locks_waiting,
            self.long_transactions_count,
            self.xact_commit_delta,
            self.xact_rollback_delta,
            self.cache_hit_ratio,
            self.deadlocks_delta,
            self.temp_files_delta,
            self.temp_bytes_delta,
            self.blk_read_time_delta,
            self.wal_bytes_delta,
            self.wal_buffers_full_delta,
            self.replication_lag_seconds,
            self.replica_count,
        )


class BaseDBAdapter(ABC):
    """Base class for database-engine telemetry adapters."""

    ENGINE = "unknown"

    def __init__(self, connection_string: str, database_name: str):
        self.connection_string = connection_string
        self.database_name = database_name
        self._previous_state: dict[str, int | float] = {}

    @abstractmethod
    async def collect(self) -> CanonicalMetrics:
        """Collect a telemetry sample in canonical format."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Return True when the adapter can connect to its engine."""

    def _delta(self, key: str, current_value: int | float | None) -> int:
        current = int(current_value or 0)
        previous = int(self._previous_state.get(key, current))
        self._previous_state[key] = current
        return max(0, current - previous)


CANONICAL_METRIC_FIELDS = [
    "active_sessions",
    "waiting_sessions",
    "lock_waiting_sessions",
    "idle_in_transaction",
    "locks_granted",
    "locks_waiting",
    "long_transactions_count",
    "xact_commit_delta",
    "xact_rollback_delta",
    "deadlocks_delta",
    "cache_hit_ratio",
    "wal_bytes_delta",
    "wal_buffers_full_delta",
    "blk_read_time_delta",
    "temp_files_delta",
    "temp_bytes_delta",
    "replication_lag_seconds",
    "replica_count",
    "mean_query_latency_ms",
]
