"""add constraints and composite index to pois

Revision ID: 004
Revises: 003
Create Date: 2026-07-03
"""
from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_pois_wilaya_category",
        "pois",
        ["wilaya_id", "category"],
    )
    op.create_check_constraint(
        "ck_poi_category",
        "pois",
        "category IN ('historical', 'natural', 'cultural', 'religious', 'museum', 'beach', 'mountain', 'park', 'market', 'other')",
    )


def downgrade() -> None:
    op.drop_index("ix_pois_wilaya_category", table_name="pois")
    op.drop_constraint("ck_poi_category", "pois", type_="check")
