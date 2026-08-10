from datetime import date
import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

PROPERTY_TYPES = ("hotel", "riad", "guesthouse", "hostel", "eco_lodge", "apartment")


class Stay(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "stays"

    __table_args__ = (
        CheckConstraint(
            f"property_type IN {PROPERTY_TYPES}",
            name="ck_stay_property_type",
        ),
        CheckConstraint(
            "price_per_night_dzd >= 0",
            name="ck_stay_price_positive",
        ),
        CheckConstraint(
            "max_guests IS NULL OR max_guests >= 1",
            name="ck_stay_max_guests",
        ),
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False, index=True
    )
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_per_night_dzd: Mapped[float] = mapped_column(Float, nullable=False)
    amenities: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    photos: Mapped[list[str] | None] = mapped_column(ARRAY(String(500)), nullable=True)
    check_in_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    max_guests: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    source_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    verified_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('french', coalesce(name, '') || ' ' || coalesce(description, '') || ' ' || coalesce(property_type, '') || ' ' || coalesce(address, ''))"  # noqa: E501
        ),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
