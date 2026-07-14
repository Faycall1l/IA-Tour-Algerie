"""015 Add seasonal fields to experiences

Revision ID: 015
Revises: 014
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015"
down_revision: str | None = "014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("experiences", sa.Column("season", sa.String(10), nullable=True))
    op.add_column("experiences", sa.Column("start_date", sa.Date, nullable=True))
    op.add_column("experiences", sa.Column("end_date", sa.Date, nullable=True))
    op.create_index("ix_experiences_season", "experiences", ["season"])
    op.create_check_constraint(
        "ck_experience_season",
        "experiences",
        "season IS NULL OR season IN ('spring', 'summer', 'autumn', 'winter')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_experience_season", "experiences")
    op.drop_index("ix_experiences_season", table_name="experiences")
    op.drop_column("experiences", "end_date")
    op.drop_column("experiences", "start_date")
    op.drop_column("experiences", "season")
