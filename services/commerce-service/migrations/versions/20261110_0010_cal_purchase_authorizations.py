"""Persist signed CAL purchase authorization receipts for cart and checkout.

Revision ID: 20261110_0010
Revises: 20261110_0009
"""
from alembic import op
import sqlalchemy as sa

revision = "20261110_0010"
down_revision = "20261110_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_cal_purchase_audits",
        sa.Column("audit_id", sa.String(length=36), primary_key=True),
        sa.Column("order_id", sa.String(length=36), sa.ForeignKey("commerce_orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("cart_id", sa.String(length=36), nullable=True),
        sa.Column("cart_version", sa.Integer(), nullable=True),
        sa.Column("buyer_user_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("catalog_product_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_id", sa.String(length=36), nullable=False),
        sa.Column("variant_id", sa.String(length=36), nullable=False),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), nullable=False),
        sa.Column("offer_snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("market_country_code", sa.String(length=2), nullable=True),
        sa.Column("destination_key_sha256", sa.String(length=64), nullable=True),
        sa.Column("fulfillment_mode", sa.String(length=32), nullable=True),
        sa.Column("display_currency", sa.String(length=3), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=False),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=180), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("decision IN ('SHOW','BLOCK','REVIEW')", name="ck_commerce_cal_purchase_decision"),
        sa.CheckConstraint("action IN ('cart_view','cart_add','cart_update','checkout')", name="ck_commerce_cal_purchase_action"),
        sa.CheckConstraint("quantity > 0", name="ck_commerce_cal_purchase_quantity"),
        sa.CheckConstraint("unit_price_minor >= 0", name="ck_commerce_cal_purchase_price"),
    )
    op.create_index("ix_commerce_cal_purchase_order", "commerce_cal_purchase_audits", ["order_id", "decision", "action"])
    op.create_index("ix_commerce_cal_purchase_buyer_created", "commerce_cal_purchase_audits", ["buyer_user_id", "created_at"])
    op.create_index("ix_commerce_cal_purchase_candidate_created", "commerce_cal_purchase_audits", ["candidate_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_commerce_cal_purchase_candidate_created", table_name="commerce_cal_purchase_audits")
    op.drop_index("ix_commerce_cal_purchase_buyer_created", table_name="commerce_cal_purchase_audits")
    op.drop_index("ix_commerce_cal_purchase_order", table_name="commerce_cal_purchase_audits")
    op.drop_table("commerce_cal_purchase_audits")
