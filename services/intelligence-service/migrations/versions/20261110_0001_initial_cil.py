"""Initial durable CIL source, evidence, outcome and CAL review schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261110_0001"
down_revision = None
branch_labels = None
depends_on = None


def json_type():
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade():
    op.create_table(
        "cil_sources",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("owner", sa.String(180), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("rights_status", sa.String(32), nullable=False),
        sa.Column("rights_reference", sa.Text(), nullable=False),
        sa.Column("permitted_purposes", json_type(), nullable=False),
        sa.Column("attribution_required", sa.Boolean(), nullable=False),
        sa.Column("attribution_text", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "cil_evidence",
        sa.Column("id", sa.String(120), primary_key=True),
        sa.Column("source_id", sa.String(120), nullable=False),
        sa.Column("grade", sa.String(2), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("locator", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cil_evidence_source_id", "cil_evidence", ["source_id"])
    op.create_table(
        "cil_recommendation_outcomes",
        sa.Column("event_id", sa.String(120), primary_key=True),
        sa.Column("product_id", sa.String(120), nullable=False),
        sa.Column("context_key", sa.String(120), nullable=False),
        sa.Column("contributor_token", sa.String(80), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("suitability", sa.String(24), nullable=False),
        sa.Column("reason_codes", json_type(), nullable=False),
        sa.Column("model_version", sa.String(240)),
        sa.Column("candidate_id", sa.String(120), nullable=False),
        sa.Column("consent_receipt_digest", sa.String(64), nullable=False),
        sa.Column("cal_receipt_digest", sa.String(64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("event_id", name="uq_cil_outcome_event"),
    )
    op.create_index("ix_cil_recommendation_outcomes_product_id", "cil_recommendation_outcomes", ["product_id"])
    op.create_index("ix_cil_recommendation_outcomes_context_key", "cil_recommendation_outcomes", ["context_key"])
    op.create_table(
        "cil_cal_review_queue",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("product_id", sa.String(120), nullable=False),
        sa.Column("context_key", sa.String(120), nullable=False),
        sa.Column("unsuitable_share", sa.Float(), nullable=False),
        sa.Column("contributor_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("verdict", sa.String(12)),
        sa.Column("decision_reference", sa.String(240)),
        sa.Column("rationale", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("product_id", "context_key", "status", name="uq_cil_cal_review_cohort_status"),
    )
    op.create_index("ix_cil_cal_review_queue_product_id", "cil_cal_review_queue", ["product_id"])
    op.create_index("ix_cil_cal_review_queue_context_key", "cil_cal_review_queue", ["context_key"])


def downgrade():
    op.drop_index("ix_cil_cal_review_queue_context_key", table_name="cil_cal_review_queue")
    op.drop_index("ix_cil_cal_review_queue_product_id", table_name="cil_cal_review_queue")
    op.drop_table("cil_cal_review_queue")
    op.drop_index("ix_cil_recommendation_outcomes_context_key", table_name="cil_recommendation_outcomes")
    op.drop_index("ix_cil_recommendation_outcomes_product_id", table_name="cil_recommendation_outcomes")
    op.drop_table("cil_recommendation_outcomes")
    op.drop_index("ix_cil_evidence_source_id", table_name="cil_evidence")
    op.drop_table("cil_evidence")
    op.drop_table("cil_sources")
