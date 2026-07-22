"""Add experience_id and stay_id to reviews for provider listing reviews.

Revision ID: 028
Revises: 027
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("experience_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("experiences.id", ondelete="SET NULL"), nullable=True))
    op.add_column("reviews", sa.Column("stay_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("stays.id", ondelete="SET NULL"), nullable=True))

    op.drop_constraint("uq_review_user_poi", "reviews", type_="unique")

    op.alter_column("reviews", "poi_id", nullable=True)

    op.create_check_constraint(
        "ck_review_one_entity",
        "reviews",
        "(poi_id IS NOT NULL)::int + (experience_id IS NOT NULL)::int + (stay_id IS NOT NULL)::int = 1",
    )

    op.create_index("ix_reviews_experience", "reviews", ["experience_id"], postgresql_where=sa.text("experience_id IS NOT NULL"))
    op.create_index("ix_reviews_stay", "reviews", ["stay_id"], postgresql_where=sa.text("stay_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_reviews_stay")
    op.drop_index("ix_reviews_experience")
    op.drop_constraint("ck_review_one_entity", "reviews", type_="check")
    op.alter_column("reviews", "poi_id", nullable=False)
    op.create_unique_constraint("uq_review_user_poi", "reviews", ["user_id", "poi_id"])
    op.drop_column("reviews", "stay_id")
    op.drop_column("reviews", "experience_id")
