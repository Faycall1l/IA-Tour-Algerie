import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.trip import ITEM_TYPES, TIME_SLOTS


class TripCreate(BaseModel):
    title: str | None = Field(None, max_length=200)
    start_date: str | None = None
    end_date: str | None = None
    total_days: int | None = Field(None, ge=1, le=365)
    total_budget_dzd: float | None = Field(None, ge=0, le=10_000_000)


class TripUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    start_date: str | None = None
    end_date: str | None = None
    total_days: int | None = Field(None, ge=1, le=365)
    status: str | None = None
    total_budget_dzd: float | None = Field(None, ge=0, le=10_000_000)


class TripItemCreate(BaseModel):
    item_type: str = Field(..., pattern=f"^({'|'.join(ITEM_TYPES)})$")
    item_id: uuid.UUID
    day_number: int = Field(1, ge=1, le=30)
    time_slot: str | None = Field(None, pattern=f"^({'|'.join(TIME_SLOTS)})$")


class TripItemUpdate(BaseModel):
    day_number: int | None = Field(None, ge=1, le=30)
    sort_order: int | None = Field(None, ge=0)
    time_slot: str | None = Field(None, pattern=f"^({'|'.join(TIME_SLOTS)})$")
    notes: str | None = None


class TripItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trip_id: uuid.UUID
    day_number: int
    sort_order: int
    time_slot: str | None
    item_type: str
    item_id: uuid.UUID
    notes: str | None
    created_at: datetime

    item_name: str | None = None
    item_image: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    estimated_duration_minutes: int | None = None
    estimated_cost_dzd: float | None = None


class DayPlan(BaseModel):
    day_number: int
    items: list[TripItemRead]
    total_distance_km: float = 0
    total_cost_dzd: float = 0
    free_slots: list[str] = []


class TripRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    start_date: str | None
    end_date: str | None
    status: str
    total_budget_dzd: float | None
    share_token: str | None = None
    created_at: datetime
    updated_at: datetime | None

    days: list[DayPlan] = []
    budget_spent: float = 0
    budget_remaining: float | None = None


class TripShareResponse(BaseModel):
    share_token: str
    share_url: str


class TripFeed(BaseModel):
    items: list[TripRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool


class OptimizationSuggestion(BaseModel):
    item_id: uuid.UUID
    reason: str
    action: str


class TripOptimizeResponse(BaseModel):
    days: list[DayPlan]
    budget_spent: float
    budget_remaining: float | None
    suggestions: list[OptimizationSuggestion] = []


class TripBriefPOI(BaseModel):
    id: uuid.UUID
    name: str
    category: str
    average_score: float | None
    total_reviews: int
    photo_url: str | None
    photo_urls: list[str] | None = None
    latitude: float | None
    longitude: float | None
    estimated_transport_cost: str | None
    is_featured: bool = False
    accessibility_score: int | None = None
    combined_score: float | None = None
    nearest_station_name: str | None = None
    distance_to_station_km: float | None = None
    walking_time_min: int | None = None
    modes_nearby: list[str] | None = None


class TripBriefExperience(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    price_dzd: float | None
    duration_hours: float | None
    provider_name: str | None


class TripBrief(BaseModel):
    wilaya_id: int
    wilaya_name: str
    top_pois: list[TripBriefPOI]
    top_experiences: list[TripBriefExperience]
    transport_advice: str | None
    tips: list[str]


class TripWhatsAppResponse(BaseModel):
    sent: bool
    phone: str | None = None
    error: str | None = None
