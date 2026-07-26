from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

EVENT_CATEGORIES = ("cultural", "food", "adventure", "hiking", "beach", "music", "religious")


class Event(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "events"

    __table_args__ = (
        Index("ix_events_wilaya", "wilaya_id"),
        Index("ix_events_month", "month"),
        CheckConstraint("month >= 1 AND month <= 12", name="ck_event_month"),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_days: Mapped[int | None] = mapped_column(Integer, default=1)
    is_recurring: Mapped[bool | None] = mapped_column(Boolean, default=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
