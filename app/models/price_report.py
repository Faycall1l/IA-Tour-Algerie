import uuid

from sqlalchemy import String, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from app.db.mixins import UUIDPkMixin, TimestampMixin


class PriceReport(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "price_reports"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    origin_wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False
    )
    dest_wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False
    )
    transport_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    price_dzd: Mapped[float] = mapped_column(Float, nullable=False)
    verified_at: Mapped[str | None] = mapped_column(String(10), nullable=True)
    confidence: Mapped[str] = mapped_column(String(10), default="user")
