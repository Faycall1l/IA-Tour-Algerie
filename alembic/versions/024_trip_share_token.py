"""024 Add share_token to trips

Enables anonymous trip sharing via unique tokens.

Revision ID: 024
Revises: 023
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "024"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("share_token", sa.String(64), nullable=True, unique=True))
    op.create_index("ix_trips_share_token", "trips", ["share_token"])


def downgrade() -> None:
    op.drop_index("ix_trips_share_token")
    op.drop_column("trips", "share_token")
