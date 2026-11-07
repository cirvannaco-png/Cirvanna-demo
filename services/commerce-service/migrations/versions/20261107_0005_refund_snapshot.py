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
    with op.batch_alter_table("commerce_orders") as batch:
        batch.add_column(
            sa.Column("refund_state", sa.String(16), nullable=False, server_default="none"),
        )
        batch.add_column(
            sa.Column("amount_refunded_minor", sa.Integer(), nullable=False, server_default="0"),
        )
        batch.add_column(
            sa.Column("payment_intent_id", sa.String(180), nullable=True),
        )
        batch.create_check_constraint(
            "ck_commerce_order_refunded_nonnegative",
            "amount_refunded_minor >= 0 AND amount_refunded_minor <= subtotal_minor",
        )
        batch.create_check_constraint(
            "ck_commerce_order_refund_state",
            "refund_state IN ('none', 'partial_refund', 'refunded')",
        )
        batch.create_index(
            "uq_commerce_order_payment_intent",
            ["payment_intent_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("commerce_orders") as batch:
        batch.drop_index("uq_commerce_order_payment_intent")
        batch.drop_constraint("ck_commerce_order_refund_state", type_="check")
        batch.drop_constraint("ck_commerce_order_refunded_nonnegative", type_="check")
        batch.drop_column("payment_intent_id")
        batch.drop_column("amount_refunded_minor")
        batch.drop_column("refund_state")
