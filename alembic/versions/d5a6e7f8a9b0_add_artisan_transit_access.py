"""add artisan_transit_access table (walking edges artisan <-> nearest transit stations)

Revision ID: d5a6e7f8a9b0
Revises: b3a9c1d2e4f5
Create Date: 2026-08-11 11:30:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d5a6e7f8a9b0"
down_revision: Union[str, None] = "b3a9c1d2e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TABLE IF NOT EXISTS artisan_transit_access ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "artisan_id UUID NOT NULL REFERENCES artisans(id) ON DELETE CASCADE, "
        "station_id UUID NOT NULL REFERENCES stations(id) ON DELETE CASCADE, "
        "distance_m DOUBLE PRECISION NOT NULL, "
        "walking_time_min DOUBLE PRECISION NOT NULL, "
        "rank INTEGER NOT NULL DEFAULT 0, "
        "source VARCHAR(30) NOT NULL DEFAULT 'spatial', "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")"
    )
    op.create_index("ix_artisan_transit_access_artisan", "artisan_transit_access", ["artisan_id"])
    op.create_index("ix_artisan_transit_access_station", "artisan_transit_access", ["station_id"])
    op.create_index(
        "ix_artisan_transit_access_artisan_rank",
        "artisan_transit_access",
        ["artisan_id", "rank"],
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_artisan_transit_access_pair "
        "ON artisan_transit_access (artisan_id, station_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS artisan_transit_access")
