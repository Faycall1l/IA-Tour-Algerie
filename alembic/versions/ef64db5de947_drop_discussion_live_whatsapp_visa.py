"""drop discussion_threads, discussion_posts, live_posts

Revision ID: ef64db5de947
Revises: 031
Create Date: 2026-07-25 11:34:24.042478
"""
from typing import Sequence, Union
from alembic import op

revision: str = "ef64db5de947"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discussion_posts CASCADE")
    op.execute("DROP TABLE IF EXISTS discussion_threads CASCADE")
    op.execute("DROP TABLE IF EXISTS live_posts CASCADE")


def downgrade() -> None:
    pass
