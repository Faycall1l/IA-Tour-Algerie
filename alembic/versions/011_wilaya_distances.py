"""wilaya_distances table — real road distances between wilayas

Revision ID: 011
Revises: 010
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wilaya_distances",
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("origin_wilaya_id", sa.Integer(), nullable=False),
        sa.Column("dest_wilaya_id", sa.Integer(), nullable=False),
        sa.Column("driving_distance_km", sa.Float(), nullable=False),
        sa.Column("driving_time_minutes", sa.Integer(), nullable=False),
        sa.Column("road_classification", sa.String(20), nullable=False),
        sa.Column("has_train_route", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "has_direct_flight", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.ForeignKeyConstraint(["origin_wilaya_id"], ["wilayas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dest_wilaya_id"], ["wilayas.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("origin_wilaya_id", "dest_wilaya_id"),
        sa.CheckConstraint(
            "road_classification IN ('autoroute', 'national', 'mountain', 'desert', 'coastal')",
            name="ck_road_classification",
        ),
        sa.CheckConstraint("driving_distance_km >= 0", name="ck_distance_positive"),
        sa.CheckConstraint("driving_time_minutes >= 0", name="ck_time_positive"),
    )


def downgrade() -> None:
    op.drop_table("wilaya_distances")
