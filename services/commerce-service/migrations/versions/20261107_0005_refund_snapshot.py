"""Add verified Stripe refund snapshots to Commerce orders.

Revision ID: 20261107_0005
Revises: 20261107_0004
"""
from alembic import op
import sqlalchemy as sa

revision = "20261107_0005"
down_revision = "20261107_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commerce_orders",
        sa.Column("refund_state", sa.String(16), nullable=False, server_default="none"),
    )
    op.add_column(
        "commerce_orders",
        sa.Column("amount_refunded_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "commerce_orders",
        sa.Column("payment_intent_id", sa.String(180), nullable=True),
    )
    op.create_index(
        "uq_commerce_order_payment_intent",
        "commerce_orders",
        ["payment_intent_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_commerce_order_payment_intent", table_name="commerce_orders")
    op.drop_column("commerce_orders", "payment_intent_id")
    op.drop_column("commerce_orders", "amount_refunded_minor")
    op.drop_column("commerce_orders", "refund_state")
