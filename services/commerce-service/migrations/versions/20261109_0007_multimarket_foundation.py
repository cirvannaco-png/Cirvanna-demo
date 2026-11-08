"""Create the multi-market quote and merchant capability foundation.

Revision ID: 20261109_0007
Revises: 20261108_0006
"""
from alembic import op
import sqlalchemy as sa

revision = "20261109_0007"
down_revision = "20261108_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("commerce_merchants", sa.Column("brand_home_country_code", sa.String(2), nullable=True))
    op.add_column("commerce_merchants", sa.Column("legal_country_code", sa.String(2), nullable=True))
    op.execute("UPDATE commerce_merchants SET legal_country_code = country_code WHERE legal_country_code IS NULL")
    op.add_column("commerce_variants", sa.Column("source_price_minor", sa.Integer(), nullable=True))
    op.add_column("commerce_variants", sa.Column("source_currency", sa.String(3), nullable=True))

    op.create_table(
        "commerce_merchant_operating_markets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("market_country_code", sa.String(2), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("display_currency", sa.String(3)),
        sa.Column("locale", sa.String(35)),
        sa.Column("activated_by", sa.String(128)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("tax_provider", sa.String(100)),
        sa.Column("tax_provider_reference", sa.String(180)),
        sa.Column("tax_capability_observed_at", sa.DateTime(timezone=True)),
        sa.Column("tax_capability_expires_at", sa.DateTime(timezone=True)),
        sa.Column("fulfillment_provider", sa.String(100)),
        sa.Column("fulfillment_provider_reference", sa.String(180)),
        sa.Column("fulfillment_capability_observed_at", sa.DateTime(timezone=True)),
        sa.Column("fulfillment_capability_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("merchant_id", "market_country_code", name="uq_commerce_merchant_market"),
        sa.CheckConstraint("state IN ('pending','active','blocked')", name="ck_commerce_market_state"),
    )
    op.create_index("ix_commerce_merchant_operating_markets_merchant_id", "commerce_merchant_operating_markets", ["merchant_id"])
    op.create_index("ix_commerce_merchant_operating_markets_market_country_code", "commerce_merchant_operating_markets", ["market_country_code"])

    op.create_table(
        "commerce_offer_fx_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("commerce_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("base_currency", sa.String(3), nullable=False),
        sa.Column("quote_currency", sa.String(3), nullable=False),
        sa.Column("rate", sa.Numeric(24, 12), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_quote_id", sa.String(180), nullable=False),
        sa.Column("rounding_rule", sa.String(40), nullable=False, server_default="HALF_UP"),
        sa.Column("spread_bps", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("variant_id", "provider", "provider_quote_id", name="uq_commerce_fx_provider_quote"),
        sa.CheckConstraint("rate > 0", name="ck_commerce_fx_rate_positive"),
    )
    op.create_index("ix_commerce_offer_fx_quotes_variant_id", "commerce_offer_fx_quotes", ["variant_id"])
    op.create_index("ix_commerce_fx_pair_expiry", "commerce_offer_fx_quotes", ["variant_id", "base_currency", "quote_currency", "expires_at"])

    op.create_table(
        "commerce_offer_fulfillment_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("commerce_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_country_code", sa.String(2), nullable=False),
        sa.Column("destination_key", sa.String(180), nullable=False),
        sa.Column("fulfillment_mode", sa.String(32), nullable=False),
        sa.Column("amount_minor", sa.Integer()),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("charge_basis", sa.String(16), nullable=False, server_default="per_unit"),
        sa.Column("distance_km", sa.Numeric(9, 2)),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_quote_id", sa.String(180), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("variant_id", "provider", "provider_quote_id", name="uq_commerce_fulfillment_provider_quote"),
        sa.CheckConstraint("status IN ('estimate','confirmed','unavailable')", name="ck_commerce_fulfillment_status"),
        sa.CheckConstraint("charge_basis IN ('per_unit','per_quote')", name="ck_commerce_fulfillment_charge_basis"),
    )
    op.create_index("ix_commerce_offer_fulfillment_quotes_variant_id", "commerce_offer_fulfillment_quotes", ["variant_id"])
    op.create_index("ix_commerce_fulfillment_lookup", "commerce_offer_fulfillment_quotes", ["variant_id", "destination_country_code", "destination_key", "fulfillment_mode", "expires_at"])

    op.create_table(
        "commerce_offer_tax_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("variant_id", sa.String(36), sa.ForeignKey("commerce_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("destination_country_code", sa.String(2), nullable=False),
        sa.Column("jurisdiction", sa.String(100), nullable=False),
        sa.Column("tax_category", sa.String(80), nullable=False),
        sa.Column("basis", sa.String(16), nullable=False),
        sa.Column("amount_minor", sa.Integer()),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("authoritative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_quote_id", sa.String(180), nullable=False),
        sa.Column("rule_version", sa.String(80)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("variant_id", "provider", "provider_quote_id", name="uq_commerce_tax_provider_quote"),
        sa.CheckConstraint("basis IN ('inclusive','exclusive')", name="ck_commerce_tax_basis"),
        sa.CheckConstraint("status IN ('estimate','confirmed','unavailable')", name="ck_commerce_tax_status"),
    )
    op.create_index("ix_commerce_offer_tax_quotes_variant_id", "commerce_offer_tax_quotes", ["variant_id"])
    op.create_index("ix_commerce_tax_lookup", "commerce_offer_tax_quotes", ["variant_id", "destination_country_code", "jurisdiction", "expires_at"])

    op.create_table(
        "commerce_market_payment_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("market_country_code", sa.String(2), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("transaction_currencies", sa.JSON(), nullable=False),
        sa.Column("settlement_currencies", sa.JSON(), nullable=False),
        sa.Column("payment_methods", sa.JSON(), nullable=False),
        sa.Column("provider_reference", sa.String(180)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("merchant_id", "market_country_code", "provider", name="uq_commerce_market_payment_provider"),
        sa.CheckConstraint("state IN ('pending','active','blocked')", name="ck_commerce_market_payment_state"),
    )
    op.create_index("ix_commerce_market_payment_capabilities_merchant_id", "commerce_market_payment_capabilities", ["merchant_id"])
    op.create_index("ix_commerce_payment_capability_market", "commerce_market_payment_capabilities", ["merchant_id", "market_country_code", "state"])


def downgrade() -> None:
    op.drop_index("ix_commerce_payment_capability_market", table_name="commerce_market_payment_capabilities")
    op.drop_index("ix_commerce_market_payment_capabilities_merchant_id", table_name="commerce_market_payment_capabilities")
    op.drop_table("commerce_market_payment_capabilities")
    op.drop_index("ix_commerce_tax_lookup", table_name="commerce_offer_tax_quotes")
    op.drop_index("ix_commerce_offer_tax_quotes_variant_id", table_name="commerce_offer_tax_quotes")
    op.drop_table("commerce_offer_tax_quotes")
    op.drop_index("ix_commerce_fulfillment_lookup", table_name="commerce_offer_fulfillment_quotes")
    op.drop_index("ix_commerce_offer_fulfillment_quotes_variant_id", table_name="commerce_offer_fulfillment_quotes")
    op.drop_table("commerce_offer_fulfillment_quotes")
    op.drop_index("ix_commerce_fx_pair_expiry", table_name="commerce_offer_fx_quotes")
    op.drop_index("ix_commerce_offer_fx_quotes_variant_id", table_name="commerce_offer_fx_quotes")
    op.drop_table("commerce_offer_fx_quotes")
    op.drop_index("ix_commerce_merchant_operating_markets_market_country_code", table_name="commerce_merchant_operating_markets")
    op.drop_index("ix_commerce_merchant_operating_markets_merchant_id", table_name="commerce_merchant_operating_markets")
    op.drop_table("commerce_merchant_operating_markets")
    op.drop_column("commerce_variants", "source_currency")
    op.drop_column("commerce_variants", "source_price_minor")
    op.drop_column("commerce_merchants", "legal_country_code")
    op.drop_column("commerce_merchants", "brand_home_country_code")
