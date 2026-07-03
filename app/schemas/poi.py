import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.poi import POI_CATEGORIES


class POICreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., pattern=f"^({'|'.join(POI_CATEGORIES)})$")
    wilaya_id: int = Field(..., ge=1, le=58)
    latitude: float | None = None
    longitude: float | None = None
    description: str | None = Field(None, max_length=2000)
    entry_fee_dzd: float | None = Field(None, ge=0, le=10_000_000)
    photo_url: str | None = Field(None, max_length=500)


class POIRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: str
    wilaya_id: int
    latitude: float | None
    longitude: float | None
    description: str | None
    entry_fee_dzd: float | None
    photo_url: str | None
    created_at: datetime
    updated_at: datetime | None
    average_score: float | None = None
    total_reviews: int = 0


class POIFeed(BaseModel):
    items: list[POIRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
