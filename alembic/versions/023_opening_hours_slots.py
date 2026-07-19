"""023 Add opening_hours_slots JSONB to pois

Stores parsed opening hours as structured weekday/time-slot data.

Revision ID: 023
Revises: 022
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "023"
down_revision: str | None = "022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pois", sa.Column("opening_hours_slots", postgresql.JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("pois", "opening_hours_slots")
