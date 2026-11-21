"""Persist CIL provider consent revocation tombstones and canonical receipt bindings."""
from alembic import op
import sqlalchemy as sa

revision = "20261120_0006"
down_revision = "20261112_0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "cil_provider_tasks",
        sa.Column("consent_receipt_id", sa.String(128), nullable=True),
    )
    op.add_column(
        "cil_provider_tasks",
        sa.Column("resource_id", sa.String(160), nullable=True),
    )
    # Existing tasks do not retain a canonical Identity receipt/resource binding.
    # Fail closed: they remain cleanup candidates and can never release results.
    op.execute(
        "UPDATE cil_provider_tasks "
        "SET revoked_at = COALESCE(revoked_at, created_at), "
        "status = 'consent_receipt_unlinked' "
        "WHERE consent_receipt_id IS NULL OR resource_id IS NULL"
    )
    op.create_table(
        "cil_provider_consent_revocations",
        sa.Column("revocation_reference", sa.String(240), primary_key=True),
        sa.Column("consent_id", sa.String(128), nullable=False),
        sa.Column("contributor_token", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "contributor_token IS NULL OR (length(contributor_token) = 76 AND substr(contributor_token, 1, 12) = 'hmac-sha256:')",
            name="ck_cil_provider_revocation_token",
        ),
    )
    op.create_index(
        "ix_cil_provider_revocations_consent_id",
        "cil_provider_consent_revocations",
        ["consent_id"],
    )
    op.create_index(
        "ix_cil_provider_revocations_consent_token",
        "cil_provider_consent_revocations",
        ["consent_id", "contributor_token"],
    )


def downgrade():
    op.drop_index(
        "ix_cil_provider_revocations_consent_token",
        table_name="cil_provider_consent_revocations",
    )
    op.drop_index(
        "ix_cil_provider_revocations_consent_id",
        table_name="cil_provider_consent_revocations",
    )
    op.drop_table("cil_provider_consent_revocations")
    op.drop_column("cil_provider_tasks", "resource_id")
    op.drop_column("cil_provider_tasks", "consent_receipt_id")
