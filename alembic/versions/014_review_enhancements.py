"""014_review_enhancements

Revision ID: 014
Revises: 013
"""
from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add columns to reviews
    op.add_column("reviews", sa.Column("sub_ratings", JSONB, nullable=True))
    op.add_column("reviews", sa.Column("helpfulness_count", sa.Integer, server_default="0", nullable=False))
    op.add_column("reviews", sa.Column("owner_response", sa.Text, nullable=True))
    op.add_column("reviews", sa.Column("response_created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("reviews", sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True))

    # Create review_votes table
    op.create_table(
        "review_votes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("review_id", UUID(as_uuid=True), sa.ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False),
        sa.Column("helpful", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "review_id", name="uq_review_vote_user"),
    )
    op.create_index("ix_review_votes_review", "review_votes", ["review_id"])


def downgrade() -> None:
    op.drop_table("review_votes")
    op.drop_column("reviews", "sub_ratings")
    op.drop_column("reviews", "helpfulness_count")
    op.drop_column("reviews", "owner_response")
    op.drop_column("reviews", "response_created_at")
    op.drop_column("reviews", "edited_at")
