"""drop bookings, circuits, notifications tables

Revision ID: ef64db5de948
Revises: ef64db5de947
Create Date: 2026-07-25 13:00:00.000000
"""
from typing import Sequence, Union
from alembic import op

revision: str = "ef64db5de948"
down_revision: Union[str, None] = "ef64db5de947"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bookings CASCADE")
    op.execute("DROP TABLE IF EXISTS circuit_items CASCADE")
    op.execute("DROP TABLE IF EXISTS circuits CASCADE")
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")


def downgrade() -> None:
    pass
