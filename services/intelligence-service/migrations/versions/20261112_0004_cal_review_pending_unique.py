"""Allow repeat CAL feedback reviews while permitting only one open request per cohort."""
from alembic import op
import sqlalchemy as sa

revision = "20261112_0004"
down_revision = "20261110_0003"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("cil_cal_review_queue") as batch:
        batch.drop_constraint("uq_cil_cal_review_cohort_status", type_="unique")
    op.create_index(
        "uq_cil_cal_review_pending_cohort",
        "cil_cal_review_queue",
        ["product_id", "context_key"],
        unique=True,
        sqlite_where=sa.text("status = 'pending'"),
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade():
    op.drop_index("uq_cil_cal_review_pending_cohort", table_name="cil_cal_review_queue")
    with op.batch_alter_table("cil_cal_review_queue") as batch:
        batch.create_unique_constraint(
            "uq_cil_cal_review_cohort_status",
            ["product_id", "context_key", "status"],
        )
