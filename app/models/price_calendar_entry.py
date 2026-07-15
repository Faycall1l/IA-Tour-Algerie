from datetime import date as date_type

from sqlalchemy import CheckConstraint, Date, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPkMixin


SUPPORTED_ENTITY_TYPES = ("experience", "stay")


class PriceCalendarEntry(UUIDPkMixin, Base):
    __tablename__ = "price_calendar"

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "date", name="uq_price_calendar_entry"),
        CheckConstraint("entity_type IN ('experience', 'stay')", name="ck_pc_entity_type"),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    price_dzd: Mapped[float] = mapped_column(Float, nullable=False)
    available_spots: Mapped[int | None] = mapped_column(Integer, nullable=True)
