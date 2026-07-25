"""add user preferences and recommendations tables

Revision ID: ef64db5de950
Revises: ef64db5de949
Create Date: 2026-07-25 20:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ef64db5de950"
down_revision: Union[str, None] = "ef64db5de949"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def table_exists(conn, name):
    r = conn.execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = :name)"
    ), {"name": name})
    return r.scalar()


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS user_preferences ("
        "id UUID PRIMARY KEY, "
        "user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE, "
        "preferred_categories JSONB, "
        "preferred_wilayas JSONB, "
        "travel_style VARCHAR(30), "
        "budget_tier VARCHAR(20), "
        "interests JSONB, "
        "avoided_categories JSONB, "
        "min_entry_fee FLOAT, "
        "max_entry_fee FLOAT, "
        "preferred_duration_min INTEGER, "
        "profile_summary TEXT, "
        "interaction_score JSONB, "
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), "
        "updated_at TIMESTAMP WITH TIME ZONE"
    ")")
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_preferences_user ON user_preferences(user_id)")

    op.execute("CREATE TABLE IF NOT EXISTS recommendations ("
        "id UUID PRIMARY KEY, "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "entity_type VARCHAR(20) NOT NULL, "
        "entity_id UUID NOT NULL, "
        "wilaya_id INTEGER, "
        "score FLOAT NOT NULL, "
        "explanation TEXT, "
        "reason_code VARCHAR(50), "
        "is_seen BOOLEAN DEFAULT false, "
        "is_dismissed BOOLEAN DEFAULT false, "
        "feedback VARCHAR(20), "
        "model_version VARCHAR(50), "
        "created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), "
        "updated_at TIMESTAMP WITH TIME ZONE"
    ")")
    op.execute("CREATE INDEX IF NOT EXISTS ix_recs_user ON recommendations(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_recs_user_score ON recommendations(user_id, score)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_recs_user_wilaya ON recommendations(user_id, wilaya_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommendations")
    op.execute("DROP TABLE IF EXISTS user_preferences")
