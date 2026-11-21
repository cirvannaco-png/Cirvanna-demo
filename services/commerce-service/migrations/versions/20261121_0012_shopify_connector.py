"""Shopify merchant-provider connection, staged snapshots and durable event links.

Revision ID: 20261121_0012
Revises: 20261112_0011
"""
from alembic import op
import sqlalchemy as sa


revision = "20261121_0012"
down_revision = "20261112_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_shopify_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_domain", sa.String(100), nullable=False),
        sa.Column("shop_gid", sa.String(180), nullable=True),
        sa.Column("shop_name", sa.String(180), nullable=True),
        sa.Column("shop_currency", sa.String(3), nullable=True),
        sa.Column("access_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("refresh_token_ciphertext", sa.Text(), nullable=True),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_scopes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("webhook_registration", sa.JSON(), nullable=False),
        sa.Column("products_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("orders_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("merchant_id", name="uq_commerce_shopify_merchant"),
        sa.UniqueConstraint("shop_domain", name="uq_commerce_shopify_domain"),
    )
    op.create_index(
        "ix_commerce_shopify_status_expiry",
        "commerce_shopify_connections",
        ["status", "access_expires_at"],
    )

    op.create_table(
        "commerce_shopify_oauth_states",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_domain", sa.String(100), nullable=False),
        sa.Column("state_sha256", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("state_sha256", name="uq_commerce_shopify_oauth_states_state_sha256"),
    )
    op.create_index(
        "ix_commerce_shopify_oauth_expiry",
        "commerce_shopify_oauth_states",
        ["expires_at", "consumed_at"],
    )

    op.create_table(
        "commerce_shopify_product_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shopify_product_gid", sa.String(180), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("handle", sa.String(255), nullable=True),
        sa.Column("vendor", sa.String(180), nullable=True),
        sa.Column("product_type", sa.String(120), nullable=True),
        sa.Column("remote_status", sa.String(24), nullable=False),
        sa.Column("remote_updated_at", sa.String(64), nullable=True),
        sa.Column("catalog_product_id", sa.String(36), nullable=True),
        sa.Column("listing_id", sa.String(36), nullable=True),
        sa.Column("mapping_state", sa.String(24), nullable=False),
        sa.Column("variants_complete", sa.Boolean(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "shopify_product_gid", name="uq_shopify_product_snapshot"),
    )
    op.create_index(
        "ix_shopify_product_snapshot_state",
        "commerce_shopify_product_snapshots",
        ["connection_id", "mapping_state"],
    )

    op.create_table(
        "commerce_shopify_variant_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_snapshot_id", sa.String(36), sa.ForeignKey("commerce_shopify_product_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shopify_variant_gid", sa.String(180), nullable=False),
        sa.Column("shopify_inventory_item_gid", sa.String(180), nullable=True),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("tracked", sa.Boolean(), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=True),
        sa.Column("on_hand_quantity", sa.Integer(), nullable=True),
        sa.Column("inventory_complete", sa.Boolean(), nullable=False),
        sa.Column("regional_prices", sa.JSON(), nullable=False),
        sa.Column("local_variant_id", sa.String(36), nullable=True),
        sa.Column("canonical_variant_id", sa.String(36), nullable=True),
        sa.Column("mapping_state", sa.String(24), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("connection_id", "shopify_variant_gid", name="uq_shopify_variant_snapshot"),
    )
    op.create_index("ix_shopify_variant_product", "commerce_shopify_variant_snapshots", ["product_snapshot_id"])
    op.create_index("ix_shopify_variant_local", "commerce_shopify_variant_snapshots", ["local_variant_id"])

    op.create_table(
        "commerce_shopify_webhook_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("shop_domain", sa.String(100), nullable=False),
        sa.Column("delivery_id", sa.String(180), nullable=False),
        sa.Column("event_id", sa.String(180), nullable=True),
        sa.Column("topic", sa.String(100), nullable=False),
        sa.Column("resource_gid", sa.String(180), nullable=True),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("shop_domain", "delivery_id", name="uq_shopify_webhook_delivery"),
    )
    op.create_index(
        "ix_shopify_webhook_pending",
        "commerce_shopify_webhook_events",
        ["state", "received_at"],
    )

    op.create_table(
        "commerce_shopify_order_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("commerce_shopify_connections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("commerce_order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_tag", sa.String(100), nullable=False),
        sa.Column("shopify_order_gid", sa.String(180), nullable=True),
        sa.Column("shopify_order_name", sa.String(80), nullable=True),
        sa.Column("financial_status", sa.String(40), nullable=True),
        sa.Column("fulfillment_status", sa.String(40), nullable=True),
        sa.Column("link_state", sa.String(24), nullable=False),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("commerce_order_id", "merchant_id", name="uq_shopify_order_link_commerce"),
        sa.UniqueConstraint("connection_id", "shopify_order_gid", name="uq_shopify_order_link_remote"),
        sa.UniqueConstraint("idempotency_tag", name="uq_commerce_shopify_order_links_idempotency_tag"),
    )
    op.create_index(
        "ix_shopify_order_link_state",
        "commerce_shopify_order_links",
        ["connection_id", "link_state"],
    )


def downgrade() -> None:
    op.drop_index("ix_shopify_order_link_state", table_name="commerce_shopify_order_links")
    op.drop_table("commerce_shopify_order_links")
    op.drop_index("ix_shopify_webhook_pending", table_name="commerce_shopify_webhook_events")
    op.drop_table("commerce_shopify_webhook_events")
    op.drop_index("ix_shopify_variant_local", table_name="commerce_shopify_variant_snapshots")
    op.drop_index("ix_shopify_variant_product", table_name="commerce_shopify_variant_snapshots")
    op.drop_table("commerce_shopify_variant_snapshots")
    op.drop_index("ix_shopify_product_snapshot_state", table_name="commerce_shopify_product_snapshots")
    op.drop_table("commerce_shopify_product_snapshots")
    op.drop_index("ix_commerce_shopify_oauth_expiry", table_name="commerce_shopify_oauth_states")
    op.drop_table("commerce_shopify_oauth_states")
    op.drop_index("ix_commerce_shopify_status_expiry", table_name="commerce_shopify_connections")
    op.drop_table("commerce_shopify_connections")
