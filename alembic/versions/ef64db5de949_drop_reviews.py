"""drop reviews table

Revision ID: ef64db5de949
Revises: ef64db5de948
Create Date: 2026-07-25 13:30:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "ef64db5de949"
down_revision: Union[str, None] = "ef64db5de948"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS review_votes CASCADE")
    op.execute("DROP TABLE IF EXISTS reviews CASCADE")


def downgrade() -> None:
    pass
