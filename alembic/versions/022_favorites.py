"""022 Add favorites (wishlist) table

Allows users to save POIs, experiences, and stays to a personal wishlist.

Revision ID: 022
Revises: 021
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "022"
down_revision: str | None = "021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


FAVORITE_ENTITY_TYPES = ("poi", "experience", "stay")


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_favorites_user_entity"),
    )
    op.create_index("ix_favorites_user", "favorites", ["user_id"])
    op.create_index("ix_favorites_entity", "favorites", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("favorites")
