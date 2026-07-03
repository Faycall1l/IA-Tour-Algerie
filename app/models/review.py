import uuid

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class Review(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "reviews"

    __table_args__ = (
        UniqueConstraint("user_id", "poi_id", name="uq_review_user_poi"),
        Index("ix_reviews_poi_score", "poi_id", "overall_score"),
        CheckConstraint(
            "overall_score >= 1 AND overall_score <= 5",
            name="ck_review_score",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    poi_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pois.id"), nullable=False
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
