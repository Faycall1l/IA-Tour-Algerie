from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

POI_CATEGORIES = (
    "historical",
    "natural",
    "cultural",
    "religious",
    "museum",
    "beach",
    "mountain",
    "park",
    "market",
    "other",
)


class POI(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "pois"

    __table_args__ = (
        Index("ix_pois_wilaya_category", "wilaya_id", "category"),
        CheckConstraint(
            f"category IN {POI_CATEGORIES}",
            name="ck_poi_category",
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False, index=True
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_fee_dzd: Mapped[float | None] = mapped_column(Float, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
