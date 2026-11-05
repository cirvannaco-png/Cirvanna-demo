"""Persist destination-bound checkout amounts and market quote snapshots.

Revision ID: 20261105_0005
Revises: 20261105_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20261105_0005"
down_revision = "20261105_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commerce_orders", sa.Column("fulfillment_total_minor", sa.Integer(), nullable=True))
    op.add_column("commerce_orders", sa.Column("tax_total_minor", sa.Integer(), nullable=True))
    op.add_column("commerce_orders", sa.Column("total_minor", sa.Integer(), nullable=True))
    op.add_column("commerce_orders", sa.Column("destination_country_code", sa.String(2), nullable=True))
    op.add_column("commerce_orders", sa.Column("destination_key", sa.String(180), nullable=True))
    op.add_column("commerce_orders", sa.Column("fulfillment_mode", sa.String(32), nullable=True))
    op.add_column("commerce_orders", sa.Column("checkout_context_hash", sa.String(64), nullable=True))
    op.add_column("commerce_orders", sa.Column("market_quote_snapshot", sa.JSON(), nullable=True))
    op.execute("UPDATE commerce_orders SET total_minor = subtotal_minor WHERE total_minor IS NULL")
    op.add_column("commerce_order_items", sa.Column("source_unit_price_minor", sa.Integer(), nullable=True))
    op.add_column("commerce_order_items", sa.Column("source_currency", sa.String(3), nullable=True))
    op.add_column("commerce_order_items", sa.Column("fx_quote_id", sa.String(36), nullable=True))
    op.create_table(
        "commerce_order_charges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id"), nullable=False),
        sa.Column("variant_id", sa.String(36), nullable=False),
        sa.Column("charge_type", sa.String(16), nullable=False),
        sa.Column("description", sa.String(180), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_amount_minor", sa.Integer(), nullable=False),
        sa.Column("source_currency", sa.String(3), nullable=False),
        sa.Column("fx_quote_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_quote_id", sa.String(180), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_minor >= 0", name="ck_commerce_order_charge_amount_nonnegative"),
        sa.CheckConstraint("charge_type IN ('fulfilment','tax')", name="ck_commerce_order_charge_type"),
    )
    op.create_index("ix_commerce_order_charges_order_id", "commerce_order_charges", ["order_id"])
    op.create_index("ix_commerce_order_charges_merchant_id", "commerce_order_charges", ["merchant_id"])


def downgrade() -> None:
    op.drop_index("ix_commerce_order_charges_merchant_id", table_name="commerce_order_charges")
    op.drop_index("ix_commerce_order_charges_order_id", table_name="commerce_order_charges")
    op.drop_table("commerce_order_charges")
    op.drop_column("commerce_order_items", "fx_quote_id")
    op.drop_column("commerce_order_items", "source_currency")
    op.drop_column("commerce_order_items", "source_unit_price_minor")
    op.drop_column("commerce_orders", "market_quote_snapshot")
    op.drop_column("commerce_orders", "checkout_context_hash")
    op.drop_column("commerce_orders", "fulfillment_mode")
    op.drop_column("commerce_orders", "destination_key")
    op.drop_column("commerce_orders", "destination_country_code")
    op.drop_column("commerce_orders", "total_minor")
    op.drop_column("commerce_orders", "tax_total_minor")
    op.drop_column("commerce_orders", "fulfillment_total_minor")
