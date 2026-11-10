"""Append-only source rights history and revocation events."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261110_0002"
down_revision = "20261110_0001"
branch_labels = None
depends_on = None


def json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "cil_source_rights_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_id", sa.String(120), nullable=False),
        sa.Column("rights_status", sa.String(32), nullable=False),
        sa.Column("permitted_purposes", json_type(), nullable=False),
        sa.Column("rights_reference", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cil_source_rights_events_source_id", "cil_source_rights_events", ["source_id"])


def downgrade():
    op.drop_index("ix_cil_source_rights_events_source_id", table_name="cil_source_rights_events")
    op.drop_table("cil_source_rights_events")
