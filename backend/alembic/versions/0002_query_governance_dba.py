"""query governance and dba copilot

Revision ID: 0002_query_governance_dba
Revises: 0001_platform_base
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_query_governance_dba"
down_revision = "0001_platform_base"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_query_policies_code"), "query_policies", ["code"], unique=False)
    op.create_index(op.f("ix_query_policies_id"), "query_policies", ["id"], unique=False)

    op.create_table(
        "query_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column("action", sa.String(length=30), nullable=False),
        sa.Column("decision", sa.String(length=30), nullable=False),
        sa.Column("risk_level", sa.String(length=30), nullable=False),
        sa.Column("reasons_json", sa.JSON(), nullable=False),
        sa.Column("recommendations_json", sa.JSON(), nullable=False),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("suggested_sql", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("execution_ms", sa.Integer(), nullable=True),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_query_reviews_id"), "query_reviews", ["id"], unique=False)

    op.create_table(
        "dba_table_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("schema_name", sa.String(length=120), nullable=False),
        sa.Column("table_name", sa.String(length=120), nullable=False),
        sa.Column("estimated_rows", sa.Integer(), nullable=False),
        sa.Column("total_size_bytes", sa.Integer(), nullable=False),
        sa.Column("columns_json", sa.JSON(), nullable=False),
        sa.Column("sensitive_columns_json", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dba_table_profiles_id"), "dba_table_profiles", ["id"], unique=False)
    op.create_index(op.f("ix_dba_table_profiles_schema_name"), "dba_table_profiles", ["schema_name"], unique=False)
    op.create_index(op.f("ix_dba_table_profiles_table_name"), "dba_table_profiles", ["table_name"], unique=False)

    op.create_table(
        "demo_customers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_code", sa.String(length=40), nullable=False),
        sa.Column("segment", sa.String(length=40), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("account_type", sa.String(length=40), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("customer_code"),
    )
    op.create_index(op.f("ix_demo_customers_customer_code"), "demo_customers", ["customer_code"], unique=False)
    op.create_index(op.f("ix_demo_customers_id"), "demo_customers", ["id"], unique=False)

    op.create_table(
        "dba_recommendations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("severity", sa.String(length=30), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["dba_table_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dba_recommendations_id"), "dba_recommendations", ["id"], unique=False)

    op.create_table(
        "demo_customer_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        sa.Column("transaction_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("merchant_category", sa.String(length=80), nullable=False),
        sa.Column("risk_flag", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["demo_customers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_demo_customer_transactions_customer_id"),
        "demo_customer_transactions",
        ["customer_id"],
        unique=False,
    )
    op.create_index(op.f("ix_demo_customer_transactions_id"), "demo_customer_transactions", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_demo_customer_transactions_id"), table_name="demo_customer_transactions")
    op.drop_index(op.f("ix_demo_customer_transactions_customer_id"), table_name="demo_customer_transactions")
    op.drop_table("demo_customer_transactions")
    op.drop_index(op.f("ix_dba_recommendations_id"), table_name="dba_recommendations")
    op.drop_table("dba_recommendations")
    op.drop_index(op.f("ix_demo_customers_id"), table_name="demo_customers")
    op.drop_index(op.f("ix_demo_customers_customer_code"), table_name="demo_customers")
    op.drop_table("demo_customers")
    op.drop_index(op.f("ix_dba_table_profiles_table_name"), table_name="dba_table_profiles")
    op.drop_index(op.f("ix_dba_table_profiles_schema_name"), table_name="dba_table_profiles")
    op.drop_index(op.f("ix_dba_table_profiles_id"), table_name="dba_table_profiles")
    op.drop_table("dba_table_profiles")
    op.drop_index(op.f("ix_query_reviews_id"), table_name="query_reviews")
    op.drop_table("query_reviews")
    op.drop_index(op.f("ix_query_policies_id"), table_name="query_policies")
    op.drop_index(op.f("ix_query_policies_code"), table_name="query_policies")
    op.drop_table("query_policies")
