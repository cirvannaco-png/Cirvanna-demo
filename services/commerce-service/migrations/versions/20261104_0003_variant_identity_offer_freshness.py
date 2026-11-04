"""Add Catalog canonical variant reference and server-observed offer freshness.

Revision ID: 20261104_0003
Revises: 20261019_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20261104_0003"
down_revision = "20261019_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commerce_variants",
        sa.Column("canonical_variant_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_commerce_variants_canonical_variant_id",
        "commerce_variants",
        ["canonical_variant_id"],
        unique=False,
    )
    op.add_column(
        "commerce_variants",
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE commerce_variants SET observed_at = updated_at WHERE observed_at IS NULL")
    with op.batch_alter_table("commerce_variants") as batch:
        batch.alter_column("observed_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.create_index(
        "ix_commerce_variant_canonical_observed",
        "commerce_variants",
        ["canonical_variant_id", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_commerce_variant_canonical_observed", table_name="commerce_variants")
    with op.batch_alter_table("commerce_variants") as batch:
        batch.drop_column("observed_at")
    op.drop_index("ix_commerce_variants_canonical_variant_id", table_name="commerce_variants")
    op.drop_column("commerce_variants", "canonical_variant_id")
