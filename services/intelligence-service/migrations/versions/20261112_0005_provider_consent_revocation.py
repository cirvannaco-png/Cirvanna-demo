"""Bind provider cleanup records to consent IDs and retain revocation state."""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0005"
down_revision = "20261112_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cil_provider_tasks",
        sa.Column("consent_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "cil_provider_tasks",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Existing unbound tasks are treated as revoked so the reaper deletes them.
    op.execute(
        "UPDATE cil_provider_tasks "
        "SET consent_id = 'legacy-unlinked', revoked_at = created_at, "
        "status = 'consent_unlinked_legacy' "
        "WHERE consent_id IS NULL"
    )
    with op.batch_alter_table("cil_provider_tasks") as batch:
        batch.alter_column("consent_id", existing_type=sa.String(128), nullable=False)
    op.create_index("ix_cil_provider_tasks_consent_id", "cil_provider_tasks", ["consent_id"])


def downgrade():
    op.drop_index("ix_cil_provider_tasks_consent_id", table_name="cil_provider_tasks")
    with op.batch_alter_table("cil_provider_tasks") as batch:
        batch.drop_column("revoked_at")
        batch.drop_column("consent_id")
