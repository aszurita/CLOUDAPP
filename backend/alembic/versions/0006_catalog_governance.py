"""catalog governance tables

Revision ID: 0006_catalog_governance
Revises: 0005_dataops_monitor
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_catalog_governance"
down_revision = "0005_dataops_monitor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.has_table(bind, "catalog_assets"):
        return

    op.create_table(
        "catalog_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_urn", sa.String(length=500), nullable=False),
        sa.Column("asset_name", sa.String(length=180), nullable=False),
        sa.Column("display_name", sa.String(length=220), nullable=False),
        sa.Column("source_system", sa.String(length=80), nullable=False),
        sa.Column("platform", sa.String(length=80), nullable=False),
        sa.Column("database_name", sa.String(length=120), nullable=True),
        sa.Column("schema_name", sa.String(length=120), nullable=True),
        sa.Column("table_name", sa.String(length=180), nullable=False),
        sa.Column("layer", sa.String(length=30), nullable=False),
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("owner", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("documentation_status", sa.String(length=40), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("sensitivity_level", sa.String(length=40), nullable=False),
        sa.Column("external_url", sa.String(length=700), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_urn"),
    )
    op.create_index(op.f("ix_catalog_assets_id"), "catalog_assets", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_assets_asset_urn"), "catalog_assets", ["asset_urn"], unique=True)
    op.create_index(op.f("ix_catalog_assets_asset_name"), "catalog_assets", ["asset_name"], unique=False)
    op.create_index(op.f("ix_catalog_assets_source_system"), "catalog_assets", ["source_system"], unique=False)
    op.create_index(op.f("ix_catalog_assets_layer"), "catalog_assets", ["layer"], unique=False)
    op.create_index(op.f("ix_catalog_assets_owner"), "catalog_assets", ["owner"], unique=False)
    op.create_index(op.f("ix_catalog_assets_sensitivity_level"), "catalog_assets", ["sensitivity_level"], unique=False)

    op.create_table(
        "catalog_columns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.String(length=180), nullable=False),
        sa.Column("data_type", sa.String(length=120), nullable=False),
        sa.Column("nullable", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("classification", sa.String(length=40), nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False),
        sa.Column("sample_safe_value", sa.String(length=180), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["catalog_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_columns_id"), "catalog_columns", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_columns_asset_id"), "catalog_columns", ["asset_id"], unique=False)
    op.create_index(op.f("ix_catalog_columns_classification"), "catalog_columns", ["classification"], unique=False)

    op.create_table(
        "catalog_owners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("owner_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=180), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=True),
        sa.Column("domain", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_key"),
    )
    op.create_index(op.f("ix_catalog_owners_id"), "catalog_owners", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_owners_owner_key"), "catalog_owners", ["owner_key"], unique=True)

    op.create_table(
        "catalog_classifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_catalog_classifications_id"), "catalog_classifications", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_classifications_code"), "catalog_classifications", ["code"], unique=True)

    op.create_table(
        "catalog_lineage_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_asset_urn", sa.String(length=500), nullable=False),
        sa.Column("target_asset_urn", sa.String(length=500), nullable=False),
        sa.Column("lineage_type", sa.String(length=80), nullable=False),
        sa.Column("transformation_name", sa.String(length=180), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_lineage_edges_id"), "catalog_lineage_edges", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_lineage_edges_source_asset_urn"), "catalog_lineage_edges", ["source_asset_urn"], unique=False)
    op.create_index(op.f("ix_catalog_lineage_edges_target_asset_urn"), "catalog_lineage_edges", ["target_asset_urn"], unique=False)

    op.create_table(
        "catalog_documentation_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["catalog_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_documentation_versions_id"), "catalog_documentation_versions", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_documentation_versions_asset_id"), "catalog_documentation_versions", ["asset_id"], unique=False)

    op.create_table(
        "catalog_sync_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("assets_seen", sa.Integer(), nullable=False),
        sa.Column("assets_created", sa.Integer(), nullable=False),
        sa.Column("assets_updated", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_catalog_sync_runs_id"), "catalog_sync_runs", ["id"], unique=False)
    op.create_index(op.f("ix_catalog_sync_runs_source"), "catalog_sync_runs", ["source"], unique=False)


def downgrade() -> None:
    op.drop_table("catalog_sync_runs")
    op.drop_table("catalog_documentation_versions")
    op.drop_table("catalog_lineage_edges")
    op.drop_table("catalog_classifications")
    op.drop_table("catalog_owners")
    op.drop_table("catalog_columns")
    op.drop_table("catalog_assets")
