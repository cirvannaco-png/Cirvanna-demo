"""Persist the exact CAL purchase authorization snapshot on orders.

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
    op.add_column(
        "commerce_orders",
        sa.Column("cal_authorization_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("commerce_orders", "cal_authorization_snapshot")
