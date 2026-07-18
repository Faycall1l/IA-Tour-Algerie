"""021 Add total_days to trips table

Adds total_days column to support circuit adoption (circuit.duration_days
maps to trip.total_days).

Revision ID: 021
Revises: 020
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "021"
down_revision: str | None = "020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("total_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "total_days")
