import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.stay import PROPERTY_TYPES


class StayCreate(BaseModel):
    name: str = Field(..., max_length=200)
    property_type: str = Field(..., pattern=f"^({'|'.join(PROPERTY_TYPES)})$")
    description: str | None = None
    wilaya_id: int = Field(..., ge=1, le=69)
    address: str | None = Field(None, max_length=500)
    latitude: float | None = None
    longitude: float | None = None
    price_per_night_dzd: float = Field(..., ge=0, le=10_000_000)
    amenities: list[str] | None = None
    photos: list[str] | None = None
    check_in_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    check_out_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    max_guests: int | None = Field(None, ge=1, le=100)
    total_rooms: int | None = Field(None, ge=1, le=1000)


class StayUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    property_type: str | None = Field(None, pattern=f"^({'|'.join(PROPERTY_TYPES)})$")
    description: str | None = None
    address: str | None = Field(None, max_length=500)
    latitude: float | None = None
    longitude: float | None = None
    price_per_night_dzd: float | None = Field(None, ge=0, le=10_000_000)
    amenities: list[str] | None = None
    photos: list[str] | None = None
    check_in_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    check_out_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    max_guests: int | None = Field(None, ge=1, le=100)
    total_rooms: int | None = Field(None, ge=1, le=1000)
    is_active: bool | None = None


class StayRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    name: str
    property_type: str
    description: str | None
    wilaya_id: int
    address: str | None
    latitude: float | None
    longitude: float | None
    price_per_night_dzd: float
    amenities: list[str] | None
    photos: list[str] | None
    check_in_time: str | None
    check_out_time: str | None
    max_guests: int | None
    total_rooms: int | None
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    provider_name: str | None = None
    provider_avatar: str | None = None


class StayFeed(BaseModel):
    items: list[StayRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
