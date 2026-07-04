import uuid

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

TRIP_STATUSES = ("active", "archived")
ITEM_TYPES = ("poi", "experience")
TIME_SLOTS = ("morning", "afternoon", "evening")


class Trip(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "trips"

    __table_args__ = (
        Index("ix_trips_user_status", "user_id", "status"),
        CheckConstraint(f"status IN {TRIP_STATUSES}", name="ck_trip_status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[str | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    total_budget_dzd: Mapped[float | None] = mapped_column(Float, nullable=True)


class TripItem(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "trip_items"

    __table_args__ = (
        Index("ix_trip_items_trip_day", "trip_id", "day_number"),
        CheckConstraint(f"item_type IN {ITEM_TYPES}", name="ck_trip_item_type"),
        CheckConstraint(
            f"time_slot IS NULL OR time_slot IN {TIME_SLOTS}",
            name="ck_trip_item_time_slot",
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_slot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
