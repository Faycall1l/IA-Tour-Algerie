import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, func, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class Review(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "reviews"

    __table_args__ = (
        UniqueConstraint("user_id", "poi_id", name="uq_review_user_poi"),
        UniqueConstraint("user_id", "experience_id", name="uq_review_user_experience"),
        UniqueConstraint("user_id", "stay_id", name="uq_review_user_stay"),
        Index("ix_reviews_poi_score", "poi_id", "overall_score"),
        Index("ix_reviews_experience", "experience_id", postgresql_where=sa.text("experience_id IS NOT NULL")),
        Index("ix_reviews_stay", "stay_id", postgresql_where=sa.text("stay_id IS NOT NULL")),
        CheckConstraint(
            "overall_score >= 1 AND overall_score <= 5",
            name="ck_review_score",
        ),
        CheckConstraint(
            "(poi_id IS NOT NULL)::int + (experience_id IS NOT NULL)::int + (stay_id IS NOT NULL)::int = 1",
            name="ck_review_one_entity",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    poi_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pois.id", ondelete="SET NULL"), nullable=True
    )
    experience_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiences.id", ondelete="SET NULL"), nullable=True
    )
    stay_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stays.id", ondelete="SET NULL"), nullable=True
    )
    overall_score: Mapped[float] = mapped_column(nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    sub_ratings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    helpfulness_count: Mapped[int] = mapped_column(Integer, default=0)
    owner_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    edited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReviewVote(UUIDPkMixin, Base):
    __tablename__ = "review_votes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    helpful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
