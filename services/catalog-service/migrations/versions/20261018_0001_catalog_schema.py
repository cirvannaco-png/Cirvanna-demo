"""Initial catalog and product-version tables.

Revision ID: 20261018_0001
Revises:
Create Date: 2026-10-18
"""
from alembic import op
import sqlalchemy as sa

revision = "20261018_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sku", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("image_urls", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("catalog_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", name="uq_catalog_products_sku"),
    )
    op.create_index("ix_catalog_products_name", "catalog_products", ["name"])
    op.create_index("ix_catalog_products_category", "catalog_products", ["category"])
    op.create_index("ix_catalog_products_brand", "catalog_products", ["brand"])
    op.create_index("ix_catalog_products_status", "catalog_products", ["status"])
    op.create_index(
        "ix_catalog_products_status_category",
        "catalog_products",
        ["status", "category"],
    )

    op.create_table(
        "catalog_product_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("change_type", sa.String(length=24), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["catalog_products.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "version", name="uq_catalog_product_version"),
    )
    op.create_index(
        "ix_catalog_product_versions_product_id",
        "catalog_product_versions",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_product_versions_product_id", table_name="catalog_product_versions")
    op.drop_table("catalog_product_versions")
    op.drop_index("ix_catalog_products_status_category", table_name="catalog_products")
    op.drop_index("ix_catalog_products_status", table_name="catalog_products")
    op.drop_index("ix_catalog_products_brand", table_name="catalog_products")
    op.drop_index("ix_catalog_products_category", table_name="catalog_products")
    op.drop_index("ix_catalog_products_name", table_name="catalog_products")
    op.drop_table("catalog_products")
