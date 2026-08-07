import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

TRAVEL_STYLES = (
    "adventure",
    "cultural",
    "relaxation",
    "nature",
    "historical",
    "culinary",
    "spiritual",
    "mixed",
)
BUDGET_TIERS = ("budget", "mid_range", "luxury", "any")


class UserPreference(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    preferred_categories: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    preferred_wilayas: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)
    travel_style: Mapped[str | None] = mapped_column(String(30), nullable=True)
    budget_tier: Mapped[str | None] = mapped_column(String(20), nullable=True)
    interests: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    avoided_categories: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    min_entry_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_entry_fee: Mapped[float | None] = mapped_column(Float, nullable=True)
    preferred_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    interaction_score: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"travel_style IS NULL OR travel_style IN {TRAVEL_STYLES}",
            name="ck_user_pref_travel_style",
        ),
        CheckConstraint(
            f"budget_tier IS NULL OR budget_tier IN {BUDGET_TIERS}",
            name="ck_user_pref_budget_tier",
        ),
    )


class Recommendation(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "recommendations"

    __table_args__ = (
        Index("ix_recs_user_score", "user_id", "score"),
        Index("ix_recs_user_wilaya", "user_id", "wilaya_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    wilaya_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_seen: Mapped[bool] = mapped_column(default=False)
    is_dismissed: Mapped[bool] = mapped_column(default=False)
    feedback: Mapped[str | None] = mapped_column(String(20), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
