"""user roles + provider profiles

Revision ID: 006
Revises: 005
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("users", sa.Column("languages", sa.ARRAY(sa.String(20)), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(1000), nullable=True))

    op.create_table(
        "provider_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True),
        sa.Column("provider_type", sa.String(20), nullable=False),
        sa.Column("is_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("experience_years", sa.Integer(), nullable=True),
        sa.Column("specializations", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("max_group_size", sa.Integer(), nullable=True),
        sa.Column("certifications", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("registration_number", sa.String(100), nullable=True),
        sa.Column("service_areas", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("team_size", sa.Integer(), nullable=True),
        sa.Column("property_name", sa.String(200), nullable=True),
        sa.Column("property_type", sa.String(50), nullable=True),
        sa.Column("amenities", sa.ARRAY(sa.String(100)), nullable=True),
        sa.Column("price_range_min", sa.Float(), nullable=True),
        sa.Column("price_range_max", sa.Float(), nullable=True),
        sa.Column("check_in_time", sa.String(5), nullable=True),
        sa.Column("check_out_time", sa.String(5), nullable=True),
        sa.Column("star_rating", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "provider_type IN ('guide', 'agency', 'hotel')",
            name="ck_profile_provider_type",
        ),
        sa.CheckConstraint(
            "property_type IS NULL OR property_type IN ('hotel', 'riad', 'guesthouse', 'hostel', 'eco_lodge')",
            name="ck_profile_property_type",
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_profiles")
    op.drop_column("users", "bio")
    op.drop_column("users", "languages")
    op.drop_column("users", "is_verified")
