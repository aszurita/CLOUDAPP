"""platform base

Revision ID: 0001_platform_base
Revises:
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_platform_base"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "environments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("region", sa.String(length=80), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_environments_code"), "environments", ["code"], unique=False)
    op.create_index(op.f("ix_environments_id"), "environments", ["id"], unique=False)

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_events_event_type"), "audit_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_audit_events_id"), "audit_events", ["id"], unique=False)

    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index(op.f("ix_platform_settings_id"), "platform_settings", ["id"], unique=False)
    op.create_index(op.f("ix_platform_settings_key"), "platform_settings", ["key"], unique=False)

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("service_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("health_url", sa.String(length=300), nullable=True),
        sa.Column("cost_estimate_usd", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_services_id"), "services", ["id"], unique=False)
    op.create_index(op.f("ix_services_name"), "services", ["name"], unique=False)

    op.create_table(
        "deployments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("commit_sha", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("deployed_by", sa.String(length=120), nullable=False),
        sa.Column("pipeline_url", sa.String(length=300), nullable=True),
        sa.Column("deployed_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_deployments_id"), "deployments", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_deployments_id"), table_name="deployments")
    op.drop_table("deployments")
    op.drop_index(op.f("ix_services_name"), table_name="services")
    op.drop_index(op.f("ix_services_id"), table_name="services")
    op.drop_table("services")
    op.drop_index(op.f("ix_platform_settings_key"), table_name="platform_settings")
    op.drop_index(op.f("ix_platform_settings_id"), table_name="platform_settings")
    op.drop_table("platform_settings")
    op.drop_index(op.f("ix_audit_events_id"), table_name="audit_events")
    op.drop_index(op.f("ix_audit_events_event_type"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index(op.f("ix_environments_id"), table_name="environments")
    op.drop_index(op.f("ix_environments_code"), table_name="environments")
    op.drop_table("environments")
