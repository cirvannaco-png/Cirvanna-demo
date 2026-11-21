"""Durable Shopify compensation and Stripe refund saga state.

Revision ID: 20261121_0014
Revises: 20261121_0013
"""
from alembic import op
import sqlalchemy as sa

revision = "20261121_0014"
down_revision = "20261121_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commerce_orders", sa.Column("fulfillment_state", sa.String(32), nullable=False, server_default="ready"))
    # Existing paid orders from connected Shopify sellers must be re-evaluated
    # against the provider reservation/order-link state before fulfilment.
    op.execute("""
        UPDATE commerce_orders
        SET fulfillment_state = 'provider_pending'
        WHERE state = 'paid'
          AND payment_state = 'paid'
          AND refund_state = 'none'
          AND EXISTS (
            SELECT 1 FROM commerce_order_items oi
            JOIN commerce_shopify_connections sc ON sc.merchant_id = oi.merchant_id
            WHERE oi.order_id = commerce_orders.id
          )
          AND EXISTS (
            SELECT 1 FROM commerce_order_items oi
            JOIN commerce_shopify_connections sc ON sc.merchant_id = oi.merchant_id
            LEFT JOIN commerce_shopify_order_links sol
              ON sol.commerce_order_id = oi.order_id AND sol.merchant_id = oi.merchant_id
            WHERE oi.order_id = commerce_orders.id
              AND (sol.id IS NULL OR sol.link_state != 'synced')
          )
    """)
    op.create_table(
        "commerce_shopify_compensation_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("commerce_order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reservation_id", sa.String(36), sa.ForeignKey("commerce_shopify_inventory_reservations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shopify_order_gid", sa.String(180), nullable=True),
        sa.Column("cancellation_job_gid", sa.String(180), nullable=True),
        sa.Column("inventory_before_json", sa.JSON(), nullable=True),
        sa.Column("inventory_expected_restore_json", sa.JSON(), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("commerce_order_id", "merchant_id", name="uq_shopify_compensation_order_merchant"),
    )
    op.create_index("ix_shopify_compensation_state_lease", "commerce_shopify_compensation_cases", ["state", "lease_until"])
    op.create_table(
        "commerce_stripe_refund_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payment_intent_id", sa.String(180), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("idempotency_key", sa.String(180), nullable=False),
        sa.Column("provider_refund_id", sa.String(180), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_commerce_stripe_refund_order"),
        sa.UniqueConstraint("idempotency_key", name="uq_commerce_stripe_refund_idempotency"),
        sa.UniqueConstraint("provider_refund_id", name="uq_commerce_stripe_refund_provider_id"),
    )
    op.create_index("ix_commerce_stripe_refund_state_lease", "commerce_stripe_refund_attempts", ["state", "lease_until"])


def downgrade() -> None:
    op.drop_index("ix_commerce_stripe_refund_state_lease", table_name="commerce_stripe_refund_attempts")
    op.drop_table("commerce_stripe_refund_attempts")
    op.drop_index("ix_shopify_compensation_state_lease", table_name="commerce_shopify_compensation_cases")
    op.drop_table("commerce_shopify_compensation_cases")
    op.drop_column("commerce_orders", "fulfillment_state")
