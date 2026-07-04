"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-03
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="traveler"),
        sa.Column("language", sa.String(5), nullable=False, server_default="fr"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("avatar_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "wilayas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("name_ar", sa.String(100), nullable=False),
        sa.Column("name_fr", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=False),
        sa.Column("name_tz", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
    )

    op.create_table(
        "local_agencies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("license_number", sa.String(50), unique=True, nullable=False),
        sa.Column("wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=False),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "pois",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=False, index=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entry_fee_dzd", sa.Float(), nullable=True),
        sa.Column("photo_url", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("family", sa.String(36), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "athar_traveler_profile",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("passport_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("encrypted_identity", sa.LargeBinary(), nullable=False),
        sa.Column("assigned_agency_id", UUID(as_uuid=True), sa.ForeignKey("local_agencies.id"), nullable=True),
        sa.Column("language_preference", sa.String(10), nullable=False, server_default="fr"),
        sa.Column("anonymous_geo_trail", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "live_posts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("photo_url", sa.String(500), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=True, index=True),
        sa.Column("poi_id", UUID(as_uuid=True), sa.ForeignKey("pois.id"), nullable=True),
        sa.Column("is_moderated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "price_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("origin_wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=False),
        sa.Column("dest_wilaya_id", sa.Integer(), sa.ForeignKey("wilayas.id"), nullable=False),
        sa.Column("transport_mode", sa.String(20), nullable=False),
        sa.Column("price_dzd", sa.Float(), nullable=False),
        sa.Column("verified_at", sa.String(10), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("poi_id", UUID(as_uuid=True), sa.ForeignKey("pois.id"), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("price_reports")
    op.drop_table("live_posts")
    op.drop_table("athar_traveler_profile")
    op.drop_table("refresh_tokens")
    op.drop_table("pois")
    op.drop_table("local_agencies")
    op.drop_table("wilayas")
    op.drop_table("users")
