"""make artisan user_id nullable for imported data

Revision ID: 3edf9d601281
Revises: 029
Create Date: 2026-07-22 15:23:59.878401
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '3edf9d601281'
down_revision: Union[str, None] = '029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('artisans', 'user_id', nullable=True)


def downgrade() -> None:
    op.alter_column('artisans', 'user_id', nullable=False)
