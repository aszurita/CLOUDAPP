"""dataops multi pipeline metadata

Revision ID: 0007_dataops_multi_pipeline
Revises: 0006_catalog_governance
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_dataops_multi_pipeline"
down_revision = "0006_catalog_governance"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    pipeline_columns = _column_names("dataops_pipelines")
    if not pipeline_columns:
        return

    with op.batch_alter_table("dataops_pipelines") as batch_op:
        if "pipeline_key" not in pipeline_columns:
            batch_op.add_column(sa.Column("pipeline_key", sa.String(length=120), nullable=True))
        if "pipeline_type" not in pipeline_columns:
            batch_op.add_column(sa.Column("pipeline_type", sa.String(length=80), nullable=True))
        if "config_json" not in pipeline_columns:
            batch_op.add_column(sa.Column("config_json", sa.JSON(), nullable=True))

    pipeline_indexes = _index_names("dataops_pipelines")
    if "ix_dataops_pipelines_pipeline_key" not in pipeline_indexes:
        op.create_index("ix_dataops_pipelines_pipeline_key", "dataops_pipelines", ["pipeline_key"], unique=True)

    op.execute("UPDATE dataops_pipelines SET pipeline_key = name WHERE pipeline_key IS NULL")
    op.execute(
        "UPDATE dataops_pipelines "
        "SET pipeline_type = 'lakehouse_bronze_silver_gold' "
        "WHERE pipeline_type IS NULL"
    )
    op.execute("UPDATE dataops_pipelines SET config_json = '{}' WHERE config_json IS NULL")

    run_columns = _column_names("dataops_pipeline_runs")
    if not run_columns:
        return

    with op.batch_alter_table("dataops_pipeline_runs") as batch_op:
        if "databricks_run_id" not in run_columns:
            batch_op.add_column(sa.Column("databricks_run_id", sa.String(length=80), nullable=True))
        if "business_run_id" not in run_columns:
            batch_op.add_column(sa.Column("business_run_id", sa.String(length=120), nullable=True))
        if "metrics_json" not in run_columns:
            batch_op.add_column(sa.Column("metrics_json", sa.JSON(), nullable=True))
        if "events_json" not in run_columns:
            batch_op.add_column(sa.Column("events_json", sa.JSON(), nullable=True))

    run_indexes = _index_names("dataops_pipeline_runs")
    if "ix_dataops_pipeline_runs_databricks_run_id" not in run_indexes:
        op.create_index("ix_dataops_pipeline_runs_databricks_run_id", "dataops_pipeline_runs", ["databricks_run_id"])
    if "ix_dataops_pipeline_runs_business_run_id" not in run_indexes:
        op.create_index("ix_dataops_pipeline_runs_business_run_id", "dataops_pipeline_runs", ["business_run_id"])

    op.execute("UPDATE dataops_pipeline_runs SET metrics_json = '[]' WHERE metrics_json IS NULL")
    op.execute("UPDATE dataops_pipeline_runs SET events_json = '[]' WHERE events_json IS NULL")


def downgrade() -> None:
    run_indexes = _index_names("dataops_pipeline_runs")
    if "ix_dataops_pipeline_runs_business_run_id" in run_indexes:
        op.drop_index("ix_dataops_pipeline_runs_business_run_id", table_name="dataops_pipeline_runs")
    if "ix_dataops_pipeline_runs_databricks_run_id" in run_indexes:
        op.drop_index("ix_dataops_pipeline_runs_databricks_run_id", table_name="dataops_pipeline_runs")

    run_columns = _column_names("dataops_pipeline_runs")
    with op.batch_alter_table("dataops_pipeline_runs") as batch_op:
        if "events_json" in run_columns:
            batch_op.drop_column("events_json")
        if "metrics_json" in run_columns:
            batch_op.drop_column("metrics_json")
        if "business_run_id" in run_columns:
            batch_op.drop_column("business_run_id")
        if "databricks_run_id" in run_columns:
            batch_op.drop_column("databricks_run_id")

    pipeline_indexes = _index_names("dataops_pipelines")
    if "ix_dataops_pipelines_pipeline_key" in pipeline_indexes:
        op.drop_index("ix_dataops_pipelines_pipeline_key", table_name="dataops_pipelines")

    pipeline_columns = _column_names("dataops_pipelines")
    with op.batch_alter_table("dataops_pipelines") as batch_op:
        if "config_json" in pipeline_columns:
            batch_op.drop_column("config_json")
        if "pipeline_type" in pipeline_columns:
            batch_op.drop_column("pipeline_type")
        if "pipeline_key" in pipeline_columns:
            batch_op.drop_column("pipeline_key")
