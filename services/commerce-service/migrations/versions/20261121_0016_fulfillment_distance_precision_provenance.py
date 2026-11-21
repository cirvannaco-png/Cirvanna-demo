"""Mark fulfilment quotes whose stored distance precision was validated.

Revision ID: 20261121_0016
Revises: 20261121_0015
"""
from alembic import op
import sqlalchemy as sa

revision = "20261121_0016"
down_revision = "20261121_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows remain NULL: Numeric(9, 2) may already have rounded their
    # original source distance, so historical precision cannot be attested.
    op.add_column(
        "commerce_offer_fulfillment_quotes",
        sa.Column("distance_precision_verified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commerce_offer_fulfillment_quotes", "distance_precision_verified_at")
