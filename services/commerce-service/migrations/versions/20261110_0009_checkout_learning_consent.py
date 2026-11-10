"""Bind paid-order learning observations to an optional verified consent receipt.

Revision ID: 20261110_0009
Revises: 20261109_0008
"""
from alembic import op
import sqlalchemy as sa

revision = "20261110_0009"
down_revision = "20261109_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commerce_orders",
        sa.Column("tal_consent_receipt_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commerce_orders", "tal_consent_receipt_id")
