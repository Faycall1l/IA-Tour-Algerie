"""026 Add user_preferences table

Adds a user_preferences table for storing user personalization data
(preferred categories, budget level, travel style, accessibility, etc.).

Revision ID: 026
Revises: 025
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "026"
down_revision: str | None = "025"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True),
        sa.Column("preferred_categories", ARRAY(sa.String(50)), nullable=True),
        sa.Column("budget_level", sa.String(20), nullable=True),
        sa.Column("travel_style", sa.String(20), nullable=True),
        sa.Column("accessibility_needed", sa.Boolean, nullable=True),
        sa.Column("preferred_transport", ARRAY(sa.String(30)), nullable=True),
        sa.Column("max_travel_distance_km", sa.Integer, nullable=True),
        sa.Column("language", sa.String(5), nullable=True, server_default="fr"),
        sa.Column("interests", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("user_preferences")
