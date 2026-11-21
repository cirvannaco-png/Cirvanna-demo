"""Durable Shopify draft-order inventory reservations for checkout.

Revision ID: 20261121_0013
Revises: 20261121_0012
"""
from alembic import op
import sqlalchemy as sa
revision = "20261121_0013"
down_revision = "20261121_0012"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "commerce_shopify_inventory_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commerce_order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reservation_key", sa.String(100), nullable=False),
        sa.Column("draft_order_gid", sa.String(180), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("commerce_order_id", "merchant_id", name="uq_shopify_inventory_reservation_order_merchant"),
        sa.UniqueConstraint("reservation_key", name="uq_shopify_inventory_reservation_key"),
        sa.UniqueConstraint("draft_order_gid", name="uq_shopify_inventory_reservation_draft"),
    )
    op.create_index("ix_shopify_inventory_reservation_state_expiry", "commerce_shopify_inventory_reservations", ["state", "expires_at"])

def downgrade() -> None:
    op.drop_index("ix_shopify_inventory_reservation_state_expiry", table_name="commerce_shopify_inventory_reservations")
    op.drop_table("commerce_shopify_inventory_reservations")
