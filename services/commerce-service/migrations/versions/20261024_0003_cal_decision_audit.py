"""Persist transaction-time CAL authorization receipts.

Revision ID: 20261024_0003
Revises: 20261019_0002
"""
from alembic import op
import sqlalchemy as sa

revision = "20261024_0003"
down_revision = "20261019_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_cal_decision_audits",
        sa.Column("audit_id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=True),
        sa.Column("buyer_user_id", sa.String(length=128), nullable=False),
        sa.Column("candidate_id", sa.String(length=128), nullable=False),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("policy_version", sa.String(length=100), nullable=True),
        sa.Column("reason_code", sa.String(length=160), nullable=True),
        sa.Column("receipt", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["commerce_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index("ix_commerce_cal_decision_audits_order_id", "commerce_cal_decision_audits", ["order_id"])
    op.create_index("ix_commerce_cal_decision_audits_buyer_user_id", "commerce_cal_decision_audits", ["buyer_user_id"])
    op.create_index("ix_commerce_cal_decision_audits_candidate_id", "commerce_cal_decision_audits", ["candidate_id"])
    op.create_index("ix_commerce_cal_decision_audits_request_id", "commerce_cal_decision_audits", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_commerce_cal_decision_audits_request_id", table_name="commerce_cal_decision_audits")
    op.drop_index("ix_commerce_cal_decision_audits_candidate_id", table_name="commerce_cal_decision_audits")
    op.drop_index("ix_commerce_cal_decision_audits_buyer_user_id", table_name="commerce_cal_decision_audits")
    op.drop_index("ix_commerce_cal_decision_audits_order_id", table_name="commerce_cal_decision_audits")
    op.drop_table("commerce_cal_decision_audits")
