import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.poi import POI_CATEGORIES


class POICreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., pattern=f"^({'|'.join(POI_CATEGORIES)})$")
    wilaya_id: int = Field(..., ge=1, le=69)
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = Field(None, max_length=2000)
    entry_fee_dzd: float | None = Field(None, ge=0, le=10_000_000)
    photo_url: str | None = Field(None, max_length=500)


class POIUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    category: str | None = Field(None, pattern=f"^({'|'.join(POI_CATEGORIES)})$")
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = Field(None, max_length=2000)
    entry_fee_dzd: float | None = Field(None, ge=0, le=10_000_000)
    photo_url: str | None = Field(None, max_length=500)
    name_ar: str | None = Field(None, max_length=200)
    name_en: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=50)
    website: str | None = Field(None, max_length=500)
    opening_hours: str | None = Field(None, max_length=500)
    cuisine: str | None = Field(None, max_length=100)
    operator: str | None = Field(None, max_length=200)
    has_parking: bool | None = None
    has_accessibility: bool | None = None
    neighborhood: str | None = Field(None, max_length=200)


class POIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    name_ar: str | None = None
    name_en: str | None = None
    category: str
    subtype: str | None = None
    wilaya_id: int
    commune: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = None
    photo_url: str | None = None
    photo_urls: list[str] | None = None
    entry_fee_dzd: float | None = None
    price_level: str | None = None
    website: str | None = None
    phone: str | None = None
    opening_hours: str | None = None
    opening_hours_slots: dict | None = None
    operator: str | None = None
    cuisine: str | None = None
    has_parking: bool | None = None
    has_accessibility: bool | None = None
    historic_civilization: str | None = None
    is_featured: bool = False
    featured_order: int | None = None
    ranking_position: int | None = None
    ranking_total: int | None = None
    suggested_duration_min: int | None = None
    neighborhood: str | None = None
    award: str | None = None
    getting_there: dict | None = None
    fun_fact: str | None = None
    fun_fact_source: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    is_favorited: bool = False


class POIBrief(BaseModel):
    """Lightweight POI for list/similar/nearby endpoints — no reviews."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    subtype: str | None = None
    wilaya_id: int
    latitude: float | None = None
    longitude: float | None = None
    photo_url: str | None = None
    is_featured: bool = False
    distance_km: float | None = None
    fun_fact: str | None = None


class POIFeed(BaseModel):
    items: list[POIRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
