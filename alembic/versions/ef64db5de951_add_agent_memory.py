"""add agent memory tables (agent_sessions, agent_memories)

Revision ID: ef64db5de951
Revises: ef64db5de950
Create Date: 2026-07-28 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "ef64db5de951"
down_revision: Union[str, None] = "ef64db5de950"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TABLE IF NOT EXISTS agent_sessions ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "agent_type VARCHAR(50) NOT NULL DEFAULT 'travel_agent', "
        "title VARCHAR(200), "
        "is_active BOOLEAN NOT NULL DEFAULT TRUE, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")")
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])

    op.execute("CREATE TABLE IF NOT EXISTS agent_memories ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "session_id UUID NOT NULL REFERENCES agent_sessions(id) ON DELETE CASCADE, "
        "memory_type VARCHAR(20) NOT NULL DEFAULT 'episodic', "
        "role VARCHAR(20), "
        "content TEXT, "
        "extra JSONB DEFAULT '{}'::jsonb, "
        "turn_index INTEGER, "
        "key VARCHAR(200), "
        "value TEXT, "
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), "
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        ")")
    op.create_index("ix_agent_memories_session_id", "agent_memories", ["session_id"])
    op.create_index("ix_agent_memories_key", "agent_memories", ["key"])
    op.create_index("ix_agent_memories_session_type", "agent_memories", ["session_id", "memory_type"])


def downgrade() -> None:
    op.drop_table("agent_memories")
    op.drop_table("agent_sessions")
