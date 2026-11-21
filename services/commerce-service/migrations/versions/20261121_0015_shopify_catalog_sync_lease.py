"""Add a durable per-store Shopify catalogue sync lease.

Revision ID: 20261121_0015
Revises: 20261121_0014
"""
from alembic import op
import sqlalchemy as sa

revision = "20261121_0015"
down_revision = "20261121_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commerce_shopify_connections", sa.Column("products_sync_lease_owner", sa.String(64), nullable=True))
    op.add_column("commerce_shopify_connections", sa.Column("products_sync_lease_until", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_shopify_products_sync_lease", "commerce_shopify_connections", ["products_sync_lease_until"])


def downgrade() -> None:
    op.drop_index("ix_shopify_products_sync_lease", table_name="commerce_shopify_connections")
    op.drop_column("commerce_shopify_connections", "products_sync_lease_until")
    op.drop_column("commerce_shopify_connections", "products_sync_lease_owner")
