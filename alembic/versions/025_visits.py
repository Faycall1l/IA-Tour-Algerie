"""025 Add user visits (check-in) table

Tracks user visits to POIs, experiences, and stays.

Revision ID: 025
Revises: 024
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "025"
down_revision: str | None = "024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("visited_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_visits_user_entity"),
    )
    op.create_index("ix_visits_user", "visits", ["user_id"])
    op.create_index("ix_visits_entity", "visits", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_table("visits")
