"""experiences table

Revision ID: 007
Revises: 006
Create Date: 2026-07-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "007"
down_revision: str | None = "006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=False, index=True),
        sa.Column("meeting_point", sa.String(500), nullable=True),
        sa.Column("meeting_point_lat", sa.Float(), nullable=True),
        sa.Column("meeting_point_lng", sa.Float(), nullable=True),
        sa.Column("price_dzd", sa.Float(), nullable=True),
        sa.Column("duration_hours", sa.Float(), nullable=True),
        sa.Column("max_participants", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(5), nullable=True),
        sa.Column("included", sa.ARRAY(sa.String(200)), nullable=True),
        sa.Column("what_to_bring", sa.ARRAY(sa.String(200)), nullable=True),
        sa.Column("photos", sa.ARRAY(sa.String(500)), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("category IN ('tour', 'workshop', 'homestay', 'hiking', 'cultural', 'food', 'adventure', 'wellness', 'other')", name="ck_experience_category"),
        sa.CheckConstraint("status IN ('draft', 'active', 'cancelled')", name="ck_experience_status"),
        sa.Index("ix_experiences_provider", "provider_id"),
        sa.Index("ix_experiences_wilaya_category", "wilaya_id", "category"),
    )


def downgrade() -> None:
    op.drop_table("experiences")
