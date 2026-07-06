import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

TRANSPORT_MODES = ("taxi", "shared_taxi", "private_taxi", "bus", "train", "metro", "tram", "cablecar", "plane", "ferry")
CONFIDENCE_TIERS = ("user", "verified", "official")


class PriceReport(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "price_reports"

    __table_args__ = (
        Index("ix_price_reports_route", "origin_wilaya_id", "dest_wilaya_id", "transport_mode"),
        CheckConstraint("price_dzd > 0", name="ck_price_positive"),
        CheckConstraint(
            f"transport_mode IN {tuple(TRANSPORT_MODES)}",
            name="ck_valid_transport_mode",
        ),
        CheckConstraint(
            f"confidence IN {tuple(CONFIDENCE_TIERS)}",
            name="ck_valid_confidence",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    origin_wilaya_id: Mapped[int] = mapped_column(Integer, ForeignKey("wilayas.id"), nullable=False)
    dest_wilaya_id: Mapped[int] = mapped_column(Integer, ForeignKey("wilayas.id"), nullable=False)
    transport_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    price_dzd: Mapped[float] = mapped_column(Float, nullable=False)
    verified_at: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[str] = mapped_column(String(10), default="user")
