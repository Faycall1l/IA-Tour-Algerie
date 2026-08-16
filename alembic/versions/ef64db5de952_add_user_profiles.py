"""add user_profiles table (persistent traveler profile)

Revision ID: ef64db5de952
Revises: d5a6e7f8a9b0
Create Date: 2026-08-16 10:00:00.000000
"""
from collections.abc import Sequence

from alembic import op

revision: str = "ef64db5de952"
down_revision: str | None = "d5a6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS user_profiles ("
        "user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
        "budget_level VARCHAR(20), "
        "interests VARCHAR(50)[], "
        "home_wilaya_id INTEGER REFERENCES wilayas(id) ON DELETE SET NULL, "
        "travel_style VARCHAR(20), "
        "preferred_language VARCHAR(5), "
        "notes TEXT, "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "CONSTRAINT ck_user_profile_budget CHECK (budget_level IS NULL OR budget_level IN ('budget', 'mid-range', 'luxury')), "
        "CONSTRAINT ck_user_profile_travel_style CHECK (travel_style IS NULL OR travel_style IN ('adventure', 'cultural', 'relax', 'family', 'food', 'nature', 'solo', 'business'))"
        ")")


def downgrade() -> None:
    op.drop_table("user_profiles")
