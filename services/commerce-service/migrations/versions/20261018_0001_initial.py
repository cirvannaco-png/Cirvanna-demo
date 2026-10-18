"""Initial durable commerce schema.

Revision ID: 20261018_0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "20261018_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_merchants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("legal_name", sa.String(180), nullable=False),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("contact_email", sa.String(254), nullable=False),
        sa.Column("verification_reference", sa.String(180)),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("commission_bps", sa.Integer(), nullable=False),
        sa.Column("decision_note", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", name="uq_commerce_merchant_owner"),
    )
    op.create_index("ix_commerce_merchants_owner_user_id", "commerce_merchants", ["owner_user_id"], unique=False)
    op.create_index("ix_commerce_merchants_state", "commerce_merchants", ["state"], unique=False)

    op.create_table(
        "commerce_listings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_product_id", sa.String(36), nullable=False),
        sa.Column("product_name", sa.String(180), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("merchant_id", "catalog_product_id", name="uq_commerce_listing_merchant_product"),
    )
    for col in ("merchant_id", "catalog_product_id", "state"):
        op.create_index(f"ix_commerce_listings_{col}", "commerce_listings", [col], unique=False)
    op.create_index("ix_commerce_listing_state_category", "commerce_listings", ["state", "category"], unique=False)

    op.create_table(
        "commerce_variants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("listing_id", sa.String(36), sa.ForeignKey("commerce_listings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("on_hand", sa.Integer(), nullable=False),
        sa.Column("reserved_qty", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("listing_id", "sku", name="uq_commerce_variant_sku"),
        sa.CheckConstraint("price_minor >= 0", name="ck_commerce_variant_price_nonnegative"),
        sa.CheckConstraint("on_hand >= 0", name="ck_commerce_variant_on_hand_nonnegative"),
        sa.CheckConstraint("reserved_qty >= 0 AND reserved_qty <= on_hand", name="ck_commerce_variant_reservation_bounds"),
    )
    for col in ("listing_id", "state"):
        op.create_index(f"ix_commerce_variants_{col}", "commerce_variants", [col], unique=False)
    op.create_index("ix_commerce_variant_listing_state", "commerce_variants", ["listing_id", "state"], unique=False)

    op.create_table(
        "commerce_inventory_movements",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("commerce_variants.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commerce_inventory_movements_variant_id", "commerce_inventory_movements", ["variant_id"], unique=False)

    op.create_table(
        "commerce_saved_products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("catalog_product_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "catalog_product_id", name="uq_commerce_saved_product"),
    )
    op.create_index("ix_commerce_saved_products_user_id", "commerce_saved_products", ["user_id"], unique=False)
    op.create_index("ix_commerce_saved_products_catalog_product_id", "commerce_saved_products", ["catalog_product_id"], unique=False)

    op.create_table(
        "commerce_carts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False, unique=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commerce_carts_user_id", "commerce_carts", ["user_id"], unique=True)

    op.create_table(
        "commerce_cart_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("cart_id", sa.String(36), sa.ForeignKey("commerce_carts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("commerce_variants.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.UniqueConstraint("cart_id", "variant_id", name="uq_commerce_cart_item"),
        sa.CheckConstraint("quantity > 0", name="ck_commerce_cart_quantity_positive"),
    )
    op.create_index("ix_commerce_cart_items_cart_id", "commerce_cart_items", ["cart_id"], unique=False)
    op.create_index("ix_commerce_cart_items_variant_id", "commerce_cart_items", ["variant_id"], unique=False)

    op.create_table(
        "commerce_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_number", sa.String(36), nullable=False, unique=True),
        sa.Column("buyer_user_id", sa.String(128), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("payment_state", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal_minor", sa.Integer(), nullable=False),
        sa.Column("commission_minor", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payment_session_id", sa.String(180), unique=True),
        sa.Column("checkout_url", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("buyer_user_id", "idempotency_key", name="uq_commerce_order_idempotency"),
        sa.CheckConstraint("subtotal_minor >= 0", name="ck_commerce_order_subtotal_nonnegative"),
    )
    op.create_index("ix_commerce_orders_buyer_user_id", "commerce_orders", ["buyer_user_id"], unique=False)
    op.create_index("ix_commerce_orders_state", "commerce_orders", ["state"], unique=False)
    op.create_index("ix_commerce_order_buyer_created", "commerce_orders", ["buyer_user_id", "created_at"], unique=False)

    op.create_table(
        "commerce_order_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id"), nullable=False),
        sa.Column("variant_id", sa.String(36), nullable=False),
        sa.Column("catalog_product_id", sa.String(36), nullable=False),
        sa.Column("product_name", sa.String(180), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False),
        sa.Column("line_total_minor", sa.Integer(), nullable=False),
        sa.Column("commission_bps", sa.Integer(), nullable=False),
        sa.Column("commission_minor", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_commerce_order_item_quantity_positive"),
        sa.CheckConstraint("unit_price_minor >= 0 AND line_total_minor >= 0", name="ck_commerce_order_item_price_nonnegative"),
    )
    for col in ("order_id", "merchant_id", "variant_id"):
        op.create_index(f"ix_commerce_order_items_{col}", "commerce_order_items", [col], unique=False)

    op.create_table(
        "commerce_stock_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("commerce_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("commerce_variants.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", "variant_id", name="uq_commerce_reservation"),
        sa.CheckConstraint("quantity > 0", name="ck_commerce_reservation_quantity_positive"),
    )
    op.create_index("ix_commerce_stock_reservations_order_id", "commerce_stock_reservations", ["order_id"], unique=False)
    op.create_index("ix_commerce_stock_reservations_variant_id", "commerce_stock_reservations", ["variant_id"], unique=False)
    op.create_index("ix_commerce_stock_reservations_state", "commerce_stock_reservations", ["state"], unique=False)
    op.create_index("ix_commerce_stock_reservations_expires_at", "commerce_stock_reservations", ["expires_at"], unique=False)

    op.create_table(
        "commerce_payment_webhook_events",
        sa.Column("event_id", sa.String(180), primary_key=True),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("commerce_payment_webhook_events")
    for name in (
        "ix_commerce_stock_reservations_expires_at", "ix_commerce_stock_reservations_state",
        "ix_commerce_stock_reservations_variant_id", "ix_commerce_stock_reservations_order_id",
    ):
        op.drop_index(name, table_name="commerce_stock_reservations")
    op.drop_table("commerce_stock_reservations")
    for name in ("ix_commerce_order_items_variant_id", "ix_commerce_order_items_merchant_id", "ix_commerce_order_items_order_id"):
        op.drop_index(name, table_name="commerce_order_items")
    op.drop_table("commerce_order_items")
    for name in ("ix_commerce_order_buyer_created", "ix_commerce_orders_state", "ix_commerce_orders_buyer_user_id"):
        op.drop_index(name, table_name="commerce_orders")
    op.drop_table("commerce_orders")
    for name in ("ix_commerce_cart_items_variant_id", "ix_commerce_cart_items_cart_id"):
        op.drop_index(name, table_name="commerce_cart_items")
    op.drop_table("commerce_cart_items")
    op.drop_index("ix_commerce_carts_user_id", table_name="commerce_carts")
    op.drop_table("commerce_carts")
    for name in ("ix_commerce_saved_products_catalog_product_id", "ix_commerce_saved_products_user_id"):
        op.drop_index(name, table_name="commerce_saved_products")
    op.drop_table("commerce_saved_products")
    op.drop_index("ix_commerce_inventory_movements_variant_id", table_name="commerce_inventory_movements")
    op.drop_table("commerce_inventory_movements")
    op.drop_index("ix_commerce_variant_listing_state", table_name="commerce_variants")
    op.drop_index("ix_commerce_variants_state", table_name="commerce_variants")
    op.drop_index("ix_commerce_variants_listing_id", table_name="commerce_variants")
    op.drop_table("commerce_variants")
    op.drop_index("ix_commerce_listing_state_category", table_name="commerce_listings")
    for col in ("state", "catalog_product_id", "merchant_id"):
        op.drop_index(f"ix_commerce_listings_{col}", table_name="commerce_listings")
    op.drop_table("commerce_listings")
    op.drop_index("ix_commerce_merchants_state", table_name="commerce_merchants")
    op.drop_index("ix_commerce_merchants_owner_user_id", table_name="commerce_merchants")
    op.drop_table("commerce_merchants")
