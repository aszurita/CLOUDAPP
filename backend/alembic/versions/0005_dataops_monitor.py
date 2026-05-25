"""dataops monitor tables

Revision ID: 0005_dataops_monitor
Revises: 0004_sentinel_tables
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_dataops_monitor"
down_revision = "0004_sentinel_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "dataops_pipelines"):
        return

    op.create_table(
        "dataops_pipelines",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("databricks_job_id", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataops_pipelines_id"), "dataops_pipelines", ["id"], unique=False)
    op.create_index(op.f("ix_dataops_pipelines_name"), "dataops_pipelines", ["name"], unique=True)

    op.create_table(
        "dataops_pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("bronze_rows", sa.Integer(), nullable=False),
        sa.Column("silver_rows", sa.Integer(), nullable=False),
        sa.Column("gold_rows", sa.Integer(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("quarantine_rows", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("failed_rules_json", sa.JSON(), nullable=False),
        sa.Column("generated_tables_json", sa.JSON(), nullable=False),
        sa.Column("databricks_run_url", sa.String(length=500), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("raw_summary_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pipeline_id"], ["dataops_pipelines.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_dataops_pipeline_runs_id"), "dataops_pipeline_runs", ["id"], unique=False)
    op.create_index(op.f("ix_dataops_pipeline_runs_pipeline_id"), "dataops_pipeline_runs", ["pipeline_id"], unique=False)
    op.create_index(op.f("ix_dataops_pipeline_runs_run_id"), "dataops_pipeline_runs", ["run_id"], unique=False)
    op.create_index(op.f("ix_dataops_pipeline_runs_status"), "dataops_pipeline_runs", ["status"], unique=False)

    op.create_table(
        "dataops_quality_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("layer", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["dataops_pipeline_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataops_quality_checks_id"), "dataops_quality_checks", ["id"], unique=False)
    op.create_index(op.f("ix_dataops_quality_checks_run_id"), "dataops_quality_checks", ["run_id"], unique=False)

    op.create_table(
        "dataops_generated_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("layer", sa.String(length=30), nullable=False),
        sa.Column("asset_name", sa.String(length=180), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["dataops_pipeline_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataops_generated_assets_id"), "dataops_generated_assets", ["id"], unique=False)
    op.create_index(op.f("ix_dataops_generated_assets_run_id"), "dataops_generated_assets", ["run_id"], unique=False)

    op.create_table(
        "dataops_quarantine_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("rule_code", sa.String(length=120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_file", sa.String(length=260), nullable=True),
        sa.Column("record_ref", sa.String(length=160), nullable=True),
        sa.Column("preview_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["dataops_pipeline_runs.run_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dataops_quarantine_events_id"), "dataops_quarantine_events", ["id"], unique=False)
    op.create_index(op.f("ix_dataops_quarantine_events_run_id"), "dataops_quarantine_events", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_table("dataops_quarantine_events")
    op.drop_table("dataops_generated_assets")
    op.drop_table("dataops_quality_checks")
    op.drop_table("dataops_pipeline_runs")
    op.drop_table("dataops_pipelines")
