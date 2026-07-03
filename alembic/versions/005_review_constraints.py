"""add constraints and indexes to reviews

Revision ID: 005
Revises: 004
Create Date: 2026-07-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_review_user_poi",
        "reviews",
        ["user_id", "poi_id"],
    )
    op.create_index(
        "ix_reviews_poi_score",
        "reviews",
        ["poi_id", "overall_score"],
    )
    op.create_check_constraint(
        "ck_review_score",
        "reviews",
        "overall_score >= 1 AND overall_score <= 5",
    )


def downgrade() -> None:
    op.drop_constraint("uq_review_user_poi", "reviews", type_="unique")
    op.drop_index("ix_reviews_poi_score", table_name="reviews")
    op.drop_constraint("ck_review_score", "reviews", type_="check")
