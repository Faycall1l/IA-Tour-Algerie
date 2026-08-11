import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPkMixin

ARTISAN_CRAFTS = (
    "pottery",
    "carpet_weaving",
    "leather_work",
    "woodwork",
    "metalwork",
    "jewelry",
    "textile",
    "basket_weaving",
    "tilework",
    "calligraphy",
    "embroidery",
    "stone_carving",
    "glasswork",
    "copper_work",
    "other",
)


class Artisan(UUIDPkMixin, Base):
    __tablename__ = "artisans"

    __table_args__ = (
        CheckConstraint(f"craft_type IN {ARTISAN_CRAFTS}", name="ck_artisan_craft_type"),
        Index("ix_artisans_wilaya", "wilaya_id"),
        Index("ix_artisans_location", "latitude", "longitude"),
        Index("ix_artisans_user", "user_id"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    craft_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False, index=True
    )
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commune: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    photos: Mapped[list[str] | None] = mapped_column(ARRAY(String(500)), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(200), nullable=True)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    specializations: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    price_range_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_range_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    accepts_custom_orders: Mapped[bool] = mapped_column(Boolean, default=True)
    has_workshop: Mapped[bool] = mapped_column(Boolean, default=True)
    accepts_visitors: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class ArtisanTransitAccess(UUIDPkMixin, Base):
    """A walking edge from an artisan workshop to its nearest transit station.

    Computed once from the transit graph (grid spatial index, 5 km cap) so the
    artisan feed can show "5 min walk to the tram stop" and routing can chain
    walking + transit legs up to a workshop. `rank` 0 = closest station.
    """

    __tablename__ = "artisan_transit_access"

    __table_args__ = (
        Index("ix_artisan_transit_access_artisan", "artisan_id"),
        Index("ix_artisan_transit_access_station", "station_id"),
        Index("ix_artisan_transit_access_artisan_rank", "artisan_id", "rank"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    artisan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("artisans.id", ondelete="CASCADE"), nullable=False
    )
    station_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stations.id", ondelete="CASCADE"), nullable=False
    )
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    walking_time_min: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="spatial")
