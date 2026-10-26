"""Add explicit catalog-attribute completeness attestation.

Revision ID: 20261024_0002
Revises: 20261018_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_0002"
down_revision = "20261018_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_products",
        sa.Column("attributes_complete", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("catalog_products", "attributes_complete")
