"""
Build online prediction features from sentinel telemetry tables.

This mirrors IA_BASES/src/build_features.py for the latest telemetry window so
FastAPI can call the Phase 5 predictor without depending on notebook code.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session


CURRENT_FEATURES = [
    "active_sessions",
    "waiting_sessions",
    "lock_waiting_sessions",
    "idle_in_transaction",
    "locks_granted",
    "locks_waiting",
    "long_transactions_count",
    "cache_hit_ratio",
    "replication_lag_seconds",
    "replica_count",
]

METRIC_COLS = [
    "active_sessions",
    "waiting_sessions",
    "lock_waiting_sessions",
    "idle_in_transaction",
    "locks_granted",
    "locks_waiting",
    "long_transactions_count",
    "cache_hit_ratio",
    "xact_commit_delta",
    "xact_rollback_delta",
    "deadlocks_delta",
    "wal_bytes_delta",
    "wal_buffers_full_delta",
    "blk_read_time_delta",
    "temp_files_delta",
    "temp_bytes_delta",
    "replication_lag_seconds",
    "replica_count",
]

QUERY_AGG_COLS = [
    "top_query_mean_exec_time",
    "top_query_calls_delta",
    "distinct_queries_active",
    "p95_mean_exec_time",
    "queries_above_1s_count",
    "query_rows_delta_sum",
    "query_wal_bytes_delta_sum",
]


def compute_slope(values: np.ndarray) -> float:
    if len(values) < 2:
        return 0.0
    x = np.arange(len(values), dtype=float)
    return float(np.polyfit(x, values.astype(float), 1)[0])


def _series_values(window: pd.DataFrame, col: str) -> np.ndarray:
    if col not in window.columns:
        return np.array([0.0])
    return window[col].fillna(0).to_numpy(dtype=float)


def compute_window_features(window: pd.DataFrame, max_connections: int) -> dict[str, float]:
    features: dict[str, float] = {}

    for col in CURRENT_FEATURES:
        vals = _series_values(window, col)
        features[col] = float(vals[-1])

    for col in METRIC_COLS + QUERY_AGG_COLS:
        vals = _series_values(window, col)
        features[f"{col}_mean"] = float(np.mean(vals))
        features[f"{col}_max"] = float(np.max(vals))
        features[f"{col}_min"] = float(np.min(vals))
        features[f"{col}_std"] = float(np.std(vals))
        features[f"{col}_last"] = float(vals[-1])
        features[f"{col}_slope"] = compute_slope(vals)
        features[f"{col}_delta"] = float(vals[-1] - vals[0])

    commit_total = (
        features.get("xact_commit_delta_mean", 0.0)
        + features.get("xact_rollback_delta_mean", 0.0)
    )
    features["rollback_ratio"] = (
        features.get("xact_rollback_delta_mean", 0.0) / commit_total if commit_total > 0 else 0.0
    )

    lock_total = features.get("locks_granted_mean", 0.0) + features.get("locks_waiting_mean", 0.0)
    features["lock_saturation_ratio"] = (
        features.get("locks_waiting_mean", 0.0) / lock_total if lock_total > 0 else 0.0
    )
    features["session_saturation"] = (
        features.get("active_sessions_last", 0.0) / max_connections if max_connections > 0 else 0.0
    )
    features["io_efficiency"] = max(0.0, min(1.0, features.get("cache_hit_ratio_mean", 0.0) / 100.0))
    return features


class FeatureBuilder:
    """Builds the current ML feature vector from sentinel tables."""

    def __init__(self, db: Session, max_connections: int = 200):
        self.db = db
        self.max_connections = max_connections

    def build_current_window(
        self,
        window_minutes: int = 10,
        database_name: str | None = None,
        min_samples: int = 2,
    ) -> dict[str, Any] | None:
        latest = self.db.execute(
            text(
                """
                SELECT MAX(collected_at)
                FROM sentinel_metric_samples
                WHERE (CAST(:database_name AS TEXT) IS NULL OR database_name = CAST(:database_name AS TEXT))
                """
            ),
            {"database_name": database_name},
        ).scalar()
        if latest is None:
            return None

        since = latest - timedelta(minutes=window_minutes)
        metric_rows = self.db.execute(
            text(
                """
                SELECT
                    collected_at, active_sessions, waiting_sessions,
                    lock_waiting_sessions, idle_in_transaction,
                    locks_granted, locks_waiting, long_transactions_count,
                    cache_hit_ratio, xact_commit_delta, xact_rollback_delta,
                    deadlocks_delta, wal_bytes_delta, wal_buffers_full_delta,
                    blk_read_time_delta, temp_files_delta, temp_bytes_delta,
                    replication_lag_seconds, replica_count
                FROM sentinel_metric_samples
                WHERE collected_at > :since
                  AND collected_at <= :latest
                  AND (CAST(:database_name AS TEXT) IS NULL OR database_name = CAST(:database_name AS TEXT))
                ORDER BY collected_at ASC
                """
            ),
            {"since": since, "latest": latest, "database_name": database_name},
        ).fetchall()
        if len(metric_rows) < min_samples:
            return None

        metrics_df = pd.DataFrame([dict(row._mapping) for row in metric_rows])
        metrics_df["collected_at"] = pd.to_datetime(metrics_df["collected_at"], utc=True)
        metrics_df = metrics_df.set_index("collected_at").sort_index()

        query_rows = self.db.execute(
            text(
                """
                SELECT
                    collected_at, queryid, calls_delta, mean_exec_time,
                    rows_delta, wal_bytes_delta
                FROM sentinel_query_samples
                WHERE collected_at > :since
                  AND collected_at <= :latest
                ORDER BY collected_at ASC
                """
            ),
            {"since": since, "latest": latest},
        ).fetchall()
        if query_rows:
            query_df = self._aggregate_query_rows(query_rows)
            metrics_df = metrics_df.join(query_df, how="left")
        for col in QUERY_AGG_COLS:
            if col not in metrics_df.columns:
                metrics_df[col] = 0.0
        metrics_df = metrics_df.fillna(0)

        features = compute_window_features(metrics_df, max_connections=self.max_connections)
        features["window_start"] = since.isoformat()
        features["window_end"] = latest.isoformat()
        features["sample_count"] = int(len(metrics_df))
        return features

    @staticmethod
    def _aggregate_query_rows(rows: list[Any]) -> pd.DataFrame:
        df = pd.DataFrame([dict(row._mapping) for row in rows])
        df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True)
        grouped = []
        for collected_at, group in df.groupby("collected_at"):
            mean_exec = group["mean_exec_time"].fillna(0).astype(float)
            top_latency = float(mean_exec.max()) if not mean_exec.empty else 0.0
            top_rows = group[mean_exec == top_latency]
            grouped.append(
                {
                    "collected_at": collected_at,
                    "top_query_mean_exec_time": top_latency,
                    "top_query_calls_delta": float(top_rows["calls_delta"].fillna(0).sum()),
                    "distinct_queries_active": int(group["queryid"].nunique()),
                    "p95_mean_exec_time": float(mean_exec.quantile(0.95)) if not mean_exec.empty else 0.0,
                    "queries_above_1s_count": int((mean_exec > 1000).sum()),
                    "query_rows_delta_sum": float(group["rows_delta"].fillna(0).sum()),
                    "query_wal_bytes_delta_sum": float(group["wal_bytes_delta"].fillna(0).sum()),
                }
            )
        if not grouped:
            return pd.DataFrame(columns=QUERY_AGG_COLS)
        return pd.DataFrame(grouped).set_index("collected_at").sort_index()
