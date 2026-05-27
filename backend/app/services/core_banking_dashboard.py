from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import Settings, get_settings
from app.services.database_inventory import database_name_from_url, host_from_url


class CoreBankingDashboardService:
    """Read-only dashboard queries for the core_banking_sim operational database."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def dashboard(self) -> dict[str, Any]:
        with self._engine().connect() as connection:
            overview = self._one(
                connection,
                """
                SELECT
                  (SELECT COUNT(*) FROM public.customers) AS customers,
                  (SELECT COUNT(*) FROM public.accounts) AS accounts,
                  (SELECT COUNT(*) FROM public.accounts WHERE status = 'active') AS active_accounts,
                  (SELECT COALESCE(SUM(balance), 0) FROM public.accounts) AS total_balance,
                  (SELECT COALESCE(SUM(available_balance), 0) FROM public.accounts) AS available_balance,
                  (SELECT COUNT(*) FROM public.transactions) AS transactions,
                  (SELECT COALESCE(SUM(amount), 0) FROM public.transactions WHERE status = 'completed') AS transaction_volume,
                  (SELECT COUNT(*) FROM public.transfers) AS transfers,
                  (SELECT COALESCE(SUM(amount), 0) FROM public.transfers WHERE status = 'completed') AS transfer_volume,
                  (SELECT COUNT(*) FROM public.account_movements) AS account_movements,
                  (SELECT COUNT(*) FROM public.service_payments) AS service_payments,
                  (SELECT COUNT(*) FROM public.audit_events) AS audit_events,
                  (SELECT COUNT(*) FROM public.batch_jobs) AS batch_jobs
                """,
            )
            latest_activity = self._one(
                connection,
                """
                SELECT GREATEST(
                  COALESCE((SELECT MAX(processed_at) FROM public.transactions), 'epoch'::timestamp),
                  COALESCE((SELECT MAX(initiated_at) FROM public.transfers), 'epoch'::timestamp),
                  COALESCE((SELECT MAX(recorded_at) FROM public.account_movements), 'epoch'::timestamp),
                  COALESCE((SELECT MAX(paid_at) FROM public.service_payments), 'epoch'::timestamp)
                ) AS latest_activity_at
                """,
            )
            timeline = self._many(
                connection,
                """
                SELECT
                  date_trunc('hour', processed_at) AS bucket,
                  COUNT(*)::bigint AS transactions,
                  COALESCE(SUM(amount), 0) AS amount
                FROM public.transactions
                WHERE processed_at >= now() - interval '24 hours'
                GROUP BY 1
                ORDER BY 1
                """,
            )
            status_mix = self._many(
                connection,
                """
                SELECT domain, status, records, amount
                FROM (
                  SELECT 'transactions' AS domain, status, COUNT(*)::bigint AS records, COALESCE(SUM(amount), 0) AS amount
                  FROM public.transactions
                  GROUP BY status
                  UNION ALL
                  SELECT 'transfers' AS domain, status, COUNT(*)::bigint AS records, COALESCE(SUM(amount), 0) AS amount
                  FROM public.transfers
                  GROUP BY status
                  UNION ALL
                  SELECT 'service_payments' AS domain, status, COUNT(*)::bigint AS records, COALESCE(SUM(amount), 0) AS amount
                  FROM public.service_payments
                  GROUP BY status
                ) mix
                ORDER BY records DESC, domain
                """,
            )
            channel_mix = self._many(
                connection,
                """
                SELECT channel, COUNT(*)::bigint AS records, COALESCE(SUM(amount), 0) AS amount
                FROM public.transactions
                GROUP BY channel
                ORDER BY records DESC
                LIMIT 8
                """,
            )
            transaction_types = self._many(
                connection,
                """
                SELECT transaction_type, COUNT(*)::bigint AS records, COALESCE(SUM(amount), 0) AS amount
                FROM public.transactions
                GROUP BY transaction_type
                ORDER BY records DESC
                LIMIT 8
                """,
            )
            transfer_types = self._many(
                connection,
                """
                SELECT transfer_type, COUNT(*)::bigint AS records, COALESCE(SUM(amount), 0) AS amount
                FROM public.transfers
                GROUP BY transfer_type
                ORDER BY records DESC
                LIMIT 8
                """,
            )
            account_segments = self._many(
                connection,
                """
                SELECT account_type, currency, COUNT(*)::bigint AS accounts, COALESCE(SUM(balance), 0) AS balance
                FROM public.accounts
                GROUP BY account_type, currency
                ORDER BY balance DESC
                LIMIT 10
                """,
            )
            risk_profiles = self._many(
                connection,
                """
                SELECT risk_profile, status, COUNT(*)::bigint AS customers
                FROM public.customers
                GROUP BY risk_profile, status
                ORDER BY customers DESC
                LIMIT 10
                """,
            )
            top_accounts = self._many(
                connection,
                """
                SELECT
                  a.account_id,
                  a.account_number,
                  a.account_type,
                  a.currency,
                  a.balance,
                  a.available_balance,
                  a.status,
                  c.full_name,
                  c.risk_profile
                FROM public.accounts a
                LEFT JOIN public.customers c ON c.customer_id = a.customer_id
                ORDER BY a.balance DESC
                LIMIT 8
                """,
            )
            latest_sentinel = self._one(
                connection,
                """
                SELECT collected_at, anomaly_score, fault_label, metrics
                FROM public.sentinel_snapshots
                ORDER BY collected_at DESC
                LIMIT 1
                """,
            )
            batches = self._many(
                connection,
                """
                SELECT batch_id, batch_type, total_records, processed, failed, status, started_at, finished_at
                FROM public.batch_jobs
                ORDER BY started_at DESC NULLS LAST
                LIMIT 8
                """,
            )

        return _json_safe(
            {
                "database": {
                    "name": database_name_from_url(self.settings.sentinel_monitor_db_url, "core_banking_sim"),
                    "host": host_from_url(self.settings.sentinel_monitor_db_url) or "localhost",
                    "engine": "postgresql",
                    "schema": "public",
                    "generated_at": datetime.utcnow(),
                    "latest_activity_at": latest_activity.get("latest_activity_at"),
                },
                "overview": overview,
                "table_inventory": self.tables(),
                "timeline": timeline,
                "status_mix": status_mix,
                "channel_mix": channel_mix,
                "transaction_types": transaction_types,
                "transfer_types": transfer_types,
                "account_segments": account_segments,
                "risk_profiles": risk_profiles,
                "top_accounts": top_accounts,
                "recent_activity": self.movements(limit=14),
                "sentinel": latest_sentinel,
                "batch_jobs": batches,
            }
        )

    def tables(self) -> list[dict[str, Any]]:
        with self._engine().connect() as connection:
            rows = self._many(
                connection,
                """
                SELECT
                  s.schemaname AS schema_name,
                  s.relname AS table_name,
                  s.n_live_tup::bigint AS estimated_rows,
                  pg_total_relation_size(s.relid)::bigint AS size_bytes,
                  COALESCE(c.column_count, 0)::int AS column_count,
                  s.last_analyze,
                  s.last_autoanalyze,
                  s.last_vacuum,
                  s.last_autovacuum
                FROM pg_stat_user_tables s
                LEFT JOIN (
                  SELECT table_schema, table_name, COUNT(*) AS column_count
                  FROM information_schema.columns
                  WHERE table_schema = 'public'
                  GROUP BY table_schema, table_name
                ) c ON c.table_schema = s.schemaname AND c.table_name = s.relname
                WHERE s.schemaname = 'public'
                ORDER BY pg_total_relation_size(s.relid) DESC, s.relname
                """,
            )
        return _json_safe(rows)

    def movements(self, limit: int = 20) -> list[dict[str, Any]]:
        safe_limit = max(1, min(limit, 80))
        with self._engine().connect() as connection:
            rows = self._many(
                connection,
                """
                (
                  SELECT
                    processed_at AS occurred_at,
                    'transaction' AS activity_type,
                    transaction_id::text AS activity_id,
                    account_id,
                    transaction_type AS operation,
                    amount,
                    currency,
                    status,
                    channel,
                    reference AS reference
                  FROM public.transactions
                  ORDER BY processed_at DESC
                  LIMIT :limit
                )
                UNION ALL
                (
                  SELECT
                    initiated_at AS occurred_at,
                    'transfer' AS activity_type,
                    transfer_id::text AS activity_id,
                    source_account_id AS account_id,
                    transfer_type AS operation,
                    amount,
                    currency,
                    status,
                    NULL AS channel,
                    target_account_id::text AS reference
                  FROM public.transfers
                  ORDER BY initiated_at DESC
                  LIMIT :limit
                )
                UNION ALL
                (
                  SELECT
                    recorded_at AS occurred_at,
                    'account_movement' AS activity_type,
                    movement_id::text AS activity_id,
                    account_id,
                    movement_type AS operation,
                    amount,
                    NULL AS currency,
                    'recorded' AS status,
                    NULL AS channel,
                    reference_id::text AS reference
                  FROM public.account_movements
                  ORDER BY recorded_at DESC
                  LIMIT :limit
                )
                ORDER BY occurred_at DESC NULLS LAST
                LIMIT :limit
                """,
                {"limit": safe_limit},
            )
        return _json_safe(rows)

    def _engine(self) -> Engine:
        if not self.settings.sentinel_monitor_db_url:
            raise RuntimeError("SENTINEL_MONITOR_DB_URL is not configured.")
        return create_engine(self.settings.sentinel_monitor_db_url, pool_pre_ping=True)

    def _one(self, connection: Any, statement: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        row = connection.execute(text(statement), params or {}).mappings().first()
        return dict(row) if row else {}

    def _many(self, connection: Any, statement: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        rows = connection.execute(text(statement), params or {}).mappings().all()
        return [dict(row) for row in rows]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
