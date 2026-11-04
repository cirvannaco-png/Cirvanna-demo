"""Add Catalog-owned canonical product variants.

Revision ID: 20261104_0002
Revises: 20261018_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20261104_0002"
down_revision = "20261018_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_product_variants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "product_id",
            sa.String(36),
            sa.ForeignKey("catalog_products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("identity_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("variant_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "product_id", "identity_key", name="uq_catalog_variant_product_identity"
        ),
    )
    op.create_index(
        "ix_catalog_product_variants_product_id",
        "catalog_product_variants",
        ["product_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_variant_product_status",
        "catalog_product_variants",
        ["product_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_variant_product_status", table_name="catalog_product_variants")
    op.drop_index("ix_catalog_product_variants_product_id", table_name="catalog_product_variants")
    op.drop_table("catalog_product_variants")
