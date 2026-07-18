from datetime import date as date_type

import sqlalchemy as sa
from sqlalchemy import ARRAY, Boolean, CheckConstraint, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

EXPERIENCE_CATEGORIES = (
    "tour",
    "workshop",
    "homestay",
    "hiking",
    "cultural",
    "food",
    "adventure",
    "wellness",
    "other",
)
EXPERIENCE_STATUSES = ("draft", "active", "cancelled")
SEASONS = ("spring", "summer", "autumn", "winter")


class Experience(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "experiences"

    __table_args__ = (
        Index("ix_experiences_provider", "provider_id"),
        Index("ix_experiences_wilaya_category", "wilaya_id", "category"),
        Index("ix_experiences_season", "season"),
        CheckConstraint(f"category IN {EXPERIENCE_CATEGORIES}", name="ck_experience_category"),
        CheckConstraint(f"status IN {EXPERIENCE_STATUSES}", name="ck_experience_status"),
        CheckConstraint(f"season IS NULL OR season IN {SEASONS}", name="ck_experience_season"),
    )

    provider_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False, index=True
    )
    meeting_point: Mapped[str | None] = mapped_column(String(500), nullable=True)
    meeting_point_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    meeting_point_lng: Mapped[float | None] = mapped_column(Float, nullable=True)

    price_dzd: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)

    language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    included: Mapped[list[str] | None] = mapped_column(ARRAY(String(200)), nullable=True)
    what_to_bring: Mapped[list[str] | None] = mapped_column(ARRAY(String(200)), nullable=True)
    photos: Mapped[list[str] | None] = mapped_column(ARRAY(String(500)), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="draft")

    season: Mapped[str | None] = mapped_column(String(10), nullable=True)
    start_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)

    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_verified: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    completion_count: Mapped[int] = mapped_column(sa.Integer, default=0)
