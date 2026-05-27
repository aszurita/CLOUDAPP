"""dashboard factory history

Revision ID: 0009_dashboard_factory_history
Revises: 0008_autopilot_reports
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_dashboard_factory_history"
down_revision = "0008_autopilot_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "dashboard_generation_history"):
        return

    op.create_table(
        "dashboard_generation_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("catalog_name", sa.String(length=120), nullable=False),
        sa.Column("schema_name", sa.String(length=120), nullable=False),
        sa.Column("table_name", sa.String(length=120), nullable=True),
        sa.Column("sql_generated", sa.Text(), nullable=True),
        sa.Column("dashboard_id", sa.String(length=200), nullable=True),
        sa.Column("dashboard_name", sa.String(length=300), nullable=True),
        sa.Column("databricks_url", sa.String(length=500), nullable=True),
        sa.Column("embed_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("chart_types", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dashboard_generation_history_id"), "dashboard_generation_history", ["id"], unique=False)
    op.create_index(
        op.f("ix_dashboard_generation_history_status"),
        "dashboard_generation_history",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_dashboard_generation_history_created_at"),
        "dashboard_generation_history",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dashboard_generation_history_created_at"), table_name="dashboard_generation_history")
    op.drop_index(op.f("ix_dashboard_generation_history_status"), table_name="dashboard_generation_history")
    op.drop_index(op.f("ix_dashboard_generation_history_id"), table_name="dashboard_generation_history")
    op.drop_table("dashboard_generation_history")
