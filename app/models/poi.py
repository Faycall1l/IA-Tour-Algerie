from sqlalchemy import ARRAY, BigInteger, Boolean, CheckConstraint, Computed, Float, ForeignKey, Index, Integer, String, Text, false
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
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
    "restaurant",
    "cafe",
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
    name_ar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    wilaya_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wilayas.id"), nullable=False, index=True
    )
    commune: Mapped[str | None] = mapped_column(String(200), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_urls: Mapped[list[str] | None] = mapped_column(ARRAY(String(500)), nullable=True)
    entry_fee_dzd: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    website: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opening_hours_slots: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    operator: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cuisine: Mapped[str | None] = mapped_column(String(200), nullable=True)
    has_parking: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_accessibility: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    historic_civilization: Mapped[str | None] = mapped_column(String(100), nullable=True)
    osm_node_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    osm_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    osm_tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    thermal_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    featured_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ranking_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ranking_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    neighborhood: Mapped[str | None] = mapped_column(String(200), nullable=True)
    award: Mapped[str | None] = mapped_column(String(200), nullable=True)
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('french', coalesce(name, '') || ' ' || coalesce(name_en, '') || ' ' || coalesce(name_ar, '') || ' ' || coalesce(description, '') || ' ' || coalesce(category, '') || ' ' || coalesce(subtype, '') || ' ' || coalesce(commune, '') || ' ' || coalesce(operator, '') || ' ' || coalesce(cuisine, '') || ' ' || coalesce(neighborhood, ''))"), nullable=True
    )
    getting_there: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fun_fact: Mapped[str | None] = mapped_column(Text, nullable=True)
    fun_fact_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
