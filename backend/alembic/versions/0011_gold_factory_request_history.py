"""gold factory request history

Revision ID: 0011_gold_factory_request_history
Revises: 0010_dashboard_factory_v2
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_gold_factory_request_history"
down_revision = "0010_dashboard_factory_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "gold_factory_requests"):
        return

    op.create_table(
        "gold_factory_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("target_catalog", sa.String(length=120), nullable=False),
        sa.Column("target_schema", sa.String(length=120), nullable=False),
        sa.Column("target_name", sa.String(length=160), nullable=False),
        sa.Column("object_type", sa.String(length=20), nullable=False),
        sa.Column("write_mode", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_by", sa.String(length=160), nullable=False),
        sa.Column("source_tables_json", sa.JSON(), nullable=False),
        sa.Column("validation_messages_json", sa.JSON(), nullable=False),
        sa.Column("raw_plan_json", sa.JSON(), nullable=False),
        sa.Column("source_sql", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        sa.Column("validation_status", sa.String(length=40), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("confidence", sa.String(length=20), nullable=True),
        sa.Column("databricks_job_id", sa.String(length=120), nullable=True),
        sa.Column("databricks_run_id", sa.String(length=120), nullable=True),
        sa.Column("databricks_run_url", sa.String(length=600), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(op.f("ix_gold_factory_requests_id"), "gold_factory_requests", ["id"], unique=False)
    op.create_index(op.f("ix_gold_factory_requests_request_id"), "gold_factory_requests", ["request_id"], unique=True)
    op.create_index(op.f("ix_gold_factory_requests_status"), "gold_factory_requests", ["status"], unique=False)
    op.create_index(op.f("ix_gold_factory_requests_databricks_job_id"), "gold_factory_requests", ["databricks_job_id"], unique=False)
    op.create_index(op.f("ix_gold_factory_requests_databricks_run_id"), "gold_factory_requests", ["databricks_run_id"], unique=False)
    op.create_index(op.f("ix_gold_factory_requests_created_at"), "gold_factory_requests", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_gold_factory_requests_created_at"), table_name="gold_factory_requests")
    op.drop_index(op.f("ix_gold_factory_requests_databricks_run_id"), table_name="gold_factory_requests")
    op.drop_index(op.f("ix_gold_factory_requests_databricks_job_id"), table_name="gold_factory_requests")
    op.drop_index(op.f("ix_gold_factory_requests_status"), table_name="gold_factory_requests")
    op.drop_index(op.f("ix_gold_factory_requests_request_id"), table_name="gold_factory_requests")
    op.drop_index(op.f("ix_gold_factory_requests_id"), table_name="gold_factory_requests")
    op.drop_table("gold_factory_requests")
