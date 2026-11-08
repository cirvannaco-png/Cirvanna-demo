"""Append-only merchant decision audit trail.

Revision ID: 20261108_0006
Revises: 20261107_0005
"""
from alembic import op
import sqlalchemy as sa

revision = "20261108_0006"
down_revision = "20261107_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_merchant_decision_audit",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("merchant_id", sa.String(36), sa.ForeignKey("commerce_merchants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("previous_state", sa.String(16), nullable=False),
        sa.Column("new_state", sa.String(16), nullable=False),
        sa.Column("previous_commission_bps", sa.Integer(), nullable=False),
        sa.Column("commission_bps", sa.Integer(), nullable=False),
        sa.Column("verification_reference", sa.String(180)),
        sa.Column("note", sa.String(500)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_commerce_merchant_decision_audit_merchant_id", "commerce_merchant_decision_audit", ["merchant_id"])
    op.create_index("ix_commerce_merchant_decision_audit_merchant_created", "commerce_merchant_decision_audit", ["merchant_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_commerce_merchant_decision_audit_merchant_created", table_name="commerce_merchant_decision_audit")
    op.drop_index("ix_commerce_merchant_decision_audit_merchant_id", table_name="commerce_merchant_decision_audit")
    op.drop_table("commerce_merchant_decision_audit")
