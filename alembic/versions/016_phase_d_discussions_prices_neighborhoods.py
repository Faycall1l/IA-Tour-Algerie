"""016 Phase D: discussions, price calendar, neighborhood index

Revision ID: 016
Revises: 015
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Discussion threads (polymorphic Q&A for POIs/experiences/stays)
    op.create_table(
        "discussion_threads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("entity_type IN ('poi', 'experience', 'stay')", name="ck_thread_entity_type"),
    )
    op.create_index("ix_discussion_threads_entity", "discussion_threads", ["entity_type", "entity_id"])
    op.create_index("ix_discussion_threads_created_by", "discussion_threads", ["created_by"])

    # Discussion posts (answers within threads)
    op.create_table(
        "discussion_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("thread_id", UUID(as_uuid=True), sa.ForeignKey("discussion_threads.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("discussion_posts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_discussion_posts_thread", "discussion_posts", ["thread_id"])
    op.create_index("ix_discussion_posts_author", "discussion_posts", ["author_id"])

    # Price calendar for experiences
    op.create_table(
        "experience_prices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("experience_id", UUID(as_uuid=True), sa.ForeignKey("experiences.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("price_dzd", sa.Float, nullable=False),
        sa.Column("available_spots", sa.Integer, nullable=True),
        sa.UniqueConstraint("experience_id", "date", name="uq_experience_price_date"),
    )
    op.create_index("ix_experience_prices_experience", "experience_prices", ["experience_id"])
    op.create_index("ix_experience_prices_date", "experience_prices", ["date"])

    # Neighborhood index on pois for neighborhood browsing
    op.create_index("ix_pois_neighborhood", "pois", ["neighborhood"])


def downgrade() -> None:
    op.drop_table("experience_prices")
    op.drop_table("discussion_posts")
    op.drop_table("discussion_threads")
    op.drop_index("ix_pois_neighborhood", table_name="pois")
