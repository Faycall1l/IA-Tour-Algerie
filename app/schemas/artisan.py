import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.artisan import ARTISAN_CRAFTS


class ArtisanCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    craft_type: str = Field(..., pattern=f"^({'|'.join(ARTISAN_CRAFTS)})$")
    description: str | None = Field(None, max_length=5000)
    wilaya_id: int = Field(..., ge=1, le=69)
    address: str | None = Field(None, max_length=500)
    commune: str | None = Field(None, max_length=200)
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=500)
    opening_hours: str | None = Field(None, max_length=200)
    years_experience: int | None = Field(None, ge=0, le=100)
    specializations: list[str] | None = None
    price_range_min: float | None = Field(None, ge=0)
    price_range_max: float | None = Field(None, ge=0)
    accepts_custom_orders: bool = True
    has_workshop: bool = True
    accepts_visitors: bool = True


class ArtisanUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    craft_type: str | None = Field(None, pattern=f"^({'|'.join(ARTISAN_CRAFTS)})$")
    description: str | None = Field(None, max_length=5000)
    wilaya_id: int | None = Field(None, ge=1, le=69)
    address: str | None = Field(None, max_length=500)
    commune: str | None = Field(None, max_length=200)
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = Field(None, max_length=20)
    whatsapp: str | None = Field(None, max_length=20)
    website: str | None = Field(None, max_length=500)
    opening_hours: str | None = Field(None, max_length=200)
    years_experience: int | None = Field(None, ge=0, le=100)
    specializations: list[str] | None = None
    price_range_min: float | None = Field(None, ge=0)
    price_range_max: float | None = Field(None, ge=0)
    accepts_custom_orders: bool | None = None
    has_workshop: bool | None = None
    accepts_visitors: bool | None = None


class ArtisanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    name: str
    craft_type: str
    description: str | None = None
    wilaya_id: int
    address: str | None = None
    commune: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    whatsapp: str | None = None
    website: str | None = None
    photos: list[str] | None = None
    opening_hours: str | None = None
    years_experience: int | None = None
    specializations: list[str] | None = None
    price_range_min: float | None = None
    price_range_max: float | None = None
    accepts_custom_orders: bool | None = None
    has_workshop: bool | None = None
    accepts_visitors: bool | None = None
    is_verified: bool | None = None
    created_at: datetime | None = None


class ArtisanFeed(BaseModel):
    items: list[ArtisanRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
