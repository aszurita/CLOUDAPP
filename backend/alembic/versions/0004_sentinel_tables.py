"""sentinel tables for DB Sentinel AI

Revision ID: 0004_sentinel_tables
Revises: 0003_dba_recommendation_category
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_sentinel_tables"
down_revision = "0003_dba_recommendation_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Telemetría cruda de métricas de base de datos ─────────────────────────
    op.create_table(
        "sentinel_metric_samples",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine", sa.String(length=20), nullable=False, server_default="postgresql"),
        sa.Column("database_name", sa.String(length=100), nullable=True),
        sa.Column("active_sessions", sa.Integer(), nullable=True),
        sa.Column("waiting_sessions", sa.Integer(), nullable=True),
        sa.Column("lock_waiting_sessions", sa.Integer(), nullable=True),
        sa.Column("idle_in_transaction", sa.Integer(), nullable=True),
        sa.Column("locks_granted", sa.Integer(), nullable=True),
        sa.Column("locks_waiting", sa.Integer(), nullable=True),
        sa.Column("long_transactions_count", sa.Integer(), nullable=True),
        sa.Column("xact_commit_delta", sa.BigInteger(), nullable=True),
        sa.Column("xact_rollback_delta", sa.BigInteger(), nullable=True),
        sa.Column("deadlocks_delta", sa.Integer(), nullable=True),
        sa.Column("cache_hit_ratio", sa.Float(), nullable=True),
        sa.Column("wal_bytes_delta", sa.BigInteger(), nullable=True),
        sa.Column("wal_buffers_full_delta", sa.Integer(), nullable=True),
        sa.Column("blk_read_time_delta", sa.Float(), nullable=True),
        sa.Column("temp_files_delta", sa.Integer(), nullable=True),
        sa.Column("temp_bytes_delta", sa.BigInteger(), nullable=True),
        sa.Column("replication_lag_seconds", sa.Float(), nullable=True),
        sa.Column("replica_count", sa.Integer(), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentinel_metrics_collected_at", "sentinel_metric_samples", ["collected_at"])
    op.create_index("ix_sentinel_metrics_engine_db", "sentinel_metric_samples", ["engine", "database_name"])

    # ── Muestras de queries (pg_stat_statements) ──────────────────────────────
    op.create_table(
        "sentinel_query_samples",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queryid", sa.BigInteger(), nullable=True),
        sa.Column("query_fingerprint", sa.Text(), nullable=True),
        sa.Column("calls_delta", sa.BigInteger(), nullable=True),
        sa.Column("mean_exec_time", sa.Float(), nullable=True),
        sa.Column("stddev_exec_time", sa.Float(), nullable=True),
        sa.Column("rows_delta", sa.BigInteger(), nullable=True),
        sa.Column("wal_bytes_delta", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentinel_queries_collected_at", "sentinel_query_samples", ["collected_at"])
    op.create_index("ix_sentinel_queries_mean_exec", "sentinel_query_samples", ["mean_exec_time"])

    # ── Incidentes detectados / predichos ─────────────────────────────────────
    op.create_table(
        "sentinel_incidents",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("predicted_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine", sa.String(length=20), nullable=True),
        sa.Column("database_name", sa.String(length=100), nullable=True),
        sa.Column("incident_type", sa.String(length=100), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("impact_level", sa.String(length=20), nullable=True),
        sa.Column("root_cause_top1", sa.String(length=100), nullable=True),
        sa.Column("root_cause_top3", sa.JSON(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("llm_explanation", sa.Text(), nullable=True),
        sa.Column("llm_recommended_actions", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dba_action_taken", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentinel_incidents_detected_at", "sentinel_incidents", ["detected_at"])
    op.create_index("ix_sentinel_incidents_status", "sentinel_incidents", ["status"])
    op.create_index("ix_sentinel_incidents_type", "sentinel_incidents", ["incident_type"])

    # ── Audit log de acciones del DBA ─────────────────────────────────────────
    op.create_table(
        "sentinel_audit_log",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), sa.ForeignKey("sentinel_incidents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action_type", sa.String(length=50), nullable=True),
        sa.Column("action_detail", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=100), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentinel_audit_incident", "sentinel_audit_log", ["incident_id"])

    # ── Resultados históricos de predicción ───────────────────────────────────
    op.create_table(
        "sentinel_prediction_results",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("predicted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True),
        sa.Column("predicted_incident_type", sa.String(length=100), nullable=True),
        sa.Column("actual_incident_type", sa.String(length=100), nullable=True),
        sa.Column("was_correct", sa.Boolean(), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sentinel_predictions_at", "sentinel_prediction_results", ["predicted_at"])


def downgrade() -> None:
    op.drop_table("sentinel_prediction_results")
    op.drop_table("sentinel_audit_log")
    op.drop_table("sentinel_incidents")
    op.drop_table("sentinel_query_samples")
    op.drop_table("sentinel_metric_samples")
