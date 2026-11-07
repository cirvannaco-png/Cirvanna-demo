"""Add transactional Commerce outbox for verified paid orders.

Revision ID: 20261107_0004
Revises: 20261104_0003
"""
from alembic import op
import sqlalchemy as sa

revision = "20261107_0004"
down_revision = "20261104_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "commerce_outbox_events",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("aggregate_type", sa.String(48), nullable=False),
        sa.Column("aggregate_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("dead_letter_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.UniqueConstraint("aggregate_type", "aggregate_id", "event_type",
                            name="uq_commerce_outbox_aggregate_event"),
    )
    op.create_index("ix_commerce_outbox_events_aggregate_id",
                    "commerce_outbox_events", ["aggregate_id"], unique=False)
    op.create_index("ix_commerce_outbox_pending",
                    "commerce_outbox_events", ["delivered_at", "dead_letter_at", "next_attempt_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_commerce_outbox_pending", table_name="commerce_outbox_events")
    op.drop_index("ix_commerce_outbox_events_aggregate_id", table_name="commerce_outbox_events")
    op.drop_table("commerce_outbox_events")
