"""Persist provider-task ownership and consent expiry for cleanup."""
from alembic import op
import sqlalchemy as sa

revision = "20261110_0003"
down_revision = "20261110_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "cil_provider_tasks",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("provider_task_id", sa.String(256), nullable=False, unique=True),
        sa.Column("provider", sa.String(40), nullable=False),
        sa.Column("contributor_token", sa.String(80), nullable=False),
        sa.Column("image_digest", sa.String(64), nullable=False),
        sa.Column("consent_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terminal_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_cil_provider_tasks_contributor_token", "cil_provider_tasks", ["contributor_token"])
    op.create_index("ix_cil_provider_tasks_created_at", "cil_provider_tasks", ["created_at"])


def downgrade():
    op.drop_index("ix_cil_provider_tasks_created_at", table_name="cil_provider_tasks")
    op.drop_index("ix_cil_provider_tasks_contributor_token", table_name="cil_provider_tasks")
    op.drop_table("cil_provider_tasks")
