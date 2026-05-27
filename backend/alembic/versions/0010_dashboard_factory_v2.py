"""dashboard factory v2 — schema-driven dashboards

Revision ID: 0010_dashboard_factory_v2
Revises: 0009_dashboard_factory_history
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_dashboard_factory_v2"
down_revision = "0009_dashboard_factory_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "dashboards"):
        return

    op.create_table(
        "dashboards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("prompt_original", sa.Text(), nullable=False),
        sa.Column("catalog_name", sa.String(length=120), nullable=False),
        sa.Column("schema_name", sa.String(length=120), nullable=False),
        sa.Column("dashboard_schema", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dashboards_id"), "dashboards", ["id"], unique=False)
    op.create_index(op.f("ix_dashboards_status"), "dashboards", ["status"], unique=False)
    op.create_index(
        op.f("ix_dashboards_created_at"), "dashboards", ["created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dashboards_created_at"), table_name="dashboards")
    op.drop_index(op.f("ix_dashboards_status"), table_name="dashboards")
    op.drop_index(op.f("ix_dashboards_id"), table_name="dashboards")
    op.drop_table("dashboards")
