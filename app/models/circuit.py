import uuid
from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class Circuit(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "circuits"
    __allow_unmapped__ = True

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    wilaya_id: Mapped[int] = mapped_column(Integer, ForeignKey("wilayas.id"), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="easy")
    total_distance_km: Mapped[float | None] = mapped_column(Float)
    total_budget_est_dzd: Mapped[float | None] = mapped_column(Float)
    photo_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    items: list["CircuitItem"] = relationship(
        back_populates="circuit", lazy="selectin",
        order_by="CircuitItem.day_number, CircuitItem.item_order",
    )
    wilaya: "Wilaya" = relationship(lazy="joined")


class CircuitItem(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "circuit_items"
    __allow_unmapped__ = True

    circuit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("circuits.id", ondelete="CASCADE"), nullable=False
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    item_order: Mapped[int] = mapped_column(Integer, default=0)
    time_slot: Mapped[str | None] = mapped_column(String(20))
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    item_match_name: Mapped[str | None] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(Text)

    circuit: Circuit = relationship(back_populates="items", lazy="joined")
