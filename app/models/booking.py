from sqlalchemy import CheckConstraint, Date, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

BOOKING_STATUSES = ("pending", "confirmed", "completed", "cancelled")


class Booking(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "bookings"

    __table_args__ = (CheckConstraint(f"status IN {BOOKING_STATUSES}", name="ck_booking_status"),)

    traveler_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    experience_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    participants: Mapped[int] = mapped_column(Integer, default=1)
    requested_date: Mapped[str | None] = mapped_column(Date, nullable=True)
