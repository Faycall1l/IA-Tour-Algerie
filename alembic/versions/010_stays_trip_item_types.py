"""stays table + extended poi categories + extended trip item types

Revision ID: 010
Revises: 009
Create Date: 2026-07-04
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create stays table
    op.create_table(
        "stays",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("provider_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("property_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=False, index=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("price_per_night_dzd", sa.Float(), nullable=False),
        sa.Column("amenities", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("photos", sa.ARRAY(sa.String(500)), nullable=True),
        sa.Column("check_in_time", sa.String(5), nullable=True),
        sa.Column("check_out_time", sa.String(5), nullable=True),
        sa.Column("max_guests", sa.Integer(), nullable=True),
        sa.Column("total_rooms", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("property_type IN ('hotel', 'riad', 'guesthouse', 'hostel', 'eco_lodge', 'apartment')", name="ck_stay_property_type"),
        sa.CheckConstraint("price_per_night_dzd >= 0", name="ck_stay_price_positive"),
        sa.CheckConstraint("max_guests IS NULL OR max_guests >= 1", name="ck_stay_max_guests"),
    )

    # Extend POI categories — drop old constraint, recreate with restaurant + cafe
    op.execute(sa.text("ALTER TABLE pois DROP CONSTRAINT IF EXISTS ck_poi_category"))
    op.create_check_constraint(
        "ck_poi_category",
        "pois",
        sa.text("category IN ('historical', 'natural', 'cultural', 'religious', 'museum', 'beach', 'mountain', 'park', 'market', 'restaurant', 'cafe', 'other')"),
    )

    # Extend TripItem types — drop old constraint, recreate with stay + restaurant + transport
    op.execute(sa.text("ALTER TABLE trip_items DROP CONSTRAINT IF EXISTS ck_trip_item_type"))
    op.create_check_constraint(
        "ck_trip_item_type",
        "trip_items",
        sa.text("item_type IN ('poi', 'experience', 'stay', 'restaurant', 'transport')"),
    )


def downgrade() -> None:
    op.drop_table("stays")

    # Revert POI categories
    op.execute(sa.text("ALTER TABLE pois DROP CONSTRAINT IF EXISTS ck_poi_category"))
    op.create_check_constraint(
        "ck_poi_category",
        "pois",
        sa.text("category IN ('historical', 'natural', 'cultural', 'religious', 'museum', 'beach', 'mountain', 'park', 'market', 'other')"),
    )

    # Revert TripItem types
    op.execute(sa.text("ALTER TABLE trip_items DROP CONSTRAINT IF EXISTS ck_trip_item_type"))
    op.create_check_constraint(
        "ck_trip_item_type",
        "trip_items",
        sa.text("item_type IN ('poi', 'experience')"),
    )
