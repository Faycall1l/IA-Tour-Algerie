"""add transfers table (walking transfer edges between stations)

Revision ID: b3a9c1d2e4f5
Revises: ef64db5de951
Create Date: 2026-08-11 09:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b3a9c1d2e4f5"
down_revision: Union[str, None] = "a47e86ebeb34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS transfers ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "from_station_id UUID NOT NULL REFERENCES stations(id) ON DELETE CASCADE, "
        "to_station_id UUID NOT NULL REFERENCES stations(id) ON DELETE CASCADE, "
        "distance_m DOUBLE PRECISION NOT NULL, "
        "walking_time_min DOUBLE PRECISION NOT NULL, "
        "source VARCHAR(30) NOT NULL DEFAULT 'spatial', "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    )
    op.create_index("ix_transfers_from_station_id", "transfers", ["from_station_id"])
    op.create_index("ix_transfers_to_station_id", "transfers", ["to_station_id"])
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_transfers_pair "
        "ON transfers (LEAST(from_station_id, to_station_id), "
        "GREATEST(from_station_id, to_station_id))"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS transfers")
