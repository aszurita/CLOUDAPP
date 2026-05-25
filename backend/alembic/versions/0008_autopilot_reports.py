"""autopilot reports

Revision ID: 0008_autopilot_reports
Revises: 0007_dataops_multi_pipeline
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_autopilot_reports"
down_revision = "0007_dataops_multi_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "autopilot_reports"):
        return

    op.create_table(
        "autopilot_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("findings_json", sa.JSON(), nullable=False),
        sa.Column("remediation_plan_json", sa.JSON(), nullable=False),
        sa.Column("infra_suggestions_json", sa.JSON(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("raw_context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_autopilot_reports_id"), "autopilot_reports", ["id"], unique=False)
    op.create_index(op.f("ix_autopilot_reports_run_id"), "autopilot_reports", ["run_id"], unique=True)
    op.create_index(op.f("ix_autopilot_reports_status"), "autopilot_reports", ["status"], unique=False)
    op.create_index(op.f("ix_autopilot_reports_risk_level"), "autopilot_reports", ["risk_level"], unique=False)

    op.create_table(
        "autopilot_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("owner", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("due_hint", sa.String(length=120), nullable=True),
        sa.Column("action_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["autopilot_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_autopilot_tasks_id"), "autopilot_tasks", ["id"], unique=False)
    op.create_index(op.f("ix_autopilot_tasks_report_id"), "autopilot_tasks", ["report_id"], unique=False)
    op.create_index(op.f("ix_autopilot_tasks_priority"), "autopilot_tasks", ["priority"], unique=False)
    op.create_index(op.f("ix_autopilot_tasks_category"), "autopilot_tasks", ["category"], unique=False)
    op.create_index(op.f("ix_autopilot_tasks_status"), "autopilot_tasks", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("autopilot_tasks")
    op.drop_table("autopilot_reports")
