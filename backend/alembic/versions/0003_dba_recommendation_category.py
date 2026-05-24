"""add category and affected_tables_json to dba_recommendations

Revision ID: 0003_dba_recommendation_category
Revises: 0002_query_governance_dba
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_dba_recommendation_category"
down_revision = "0002_query_governance_dba"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("dba_recommendations") as batch_op:
        batch_op.add_column(sa.Column("category", sa.String(30), nullable=False, server_default="operations"))
        batch_op.add_column(sa.Column("affected_tables_json", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("dba_recommendations") as batch_op:
        batch_op.drop_column("affected_tables_json")
        batch_op.drop_column("category")
