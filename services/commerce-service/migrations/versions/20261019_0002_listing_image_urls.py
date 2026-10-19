"""Add canonical catalog image snapshot to commerce listings.

Revision ID: 20261019_0002
Revises: 20261018_0001
"""
from alembic import op
import sqlalchemy as sa

revision = "20261019_0002"
down_revision = "20261018_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commerce_listings",
        sa.Column("image_urls", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )


def downgrade() -> None:
    op.drop_column("commerce_listings", "image_urls")
