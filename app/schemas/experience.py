import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.experience import EXPERIENCE_CATEGORIES, EXPERIENCE_STATUSES


class ExperienceCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    category: str = Field(..., pattern=f"^({'|'.join(EXPERIENCE_CATEGORIES)})$")
    description: str | None = Field(None, max_length=5000)
    wilaya_id: int = Field(..., ge=1, le=58)
    meeting_point: str | None = Field(None, max_length=500)
    meeting_point_lat: float | None = None
    meeting_point_lng: float | None = None
    price_dzd: float | None = Field(None, ge=0, le=10_000_000)
    duration_hours: float | None = Field(None, gt=0, le=720)
    max_participants: int | None = Field(None, ge=1, le=1000)
    language: str | None = Field(None, max_length=5)
    included: list[str] | None = None
    what_to_bring: list[str] | None = None
    status: str = "draft"


class ExperienceUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    category: str | None = Field(None, pattern=f"^({'|'.join(EXPERIENCE_CATEGORIES)})$")
    description: str | None = Field(None, max_length=5000)
    meeting_point: str | None = Field(None, max_length=500)
    meeting_point_lat: float | None = None
    meeting_point_lng: float | None = None
    price_dzd: float | None = Field(None, ge=0, le=10_000_000)
    duration_hours: float | None = Field(None, gt=0, le=720)
    max_participants: int | None = Field(None, ge=1, le=1000)
    language: str | None = Field(None, max_length=5)
    included: list[str] | None = None
    what_to_bring: list[str] | None = None
    status: str | None = Field(None, pattern=f"^({'|'.join(EXPERIENCE_STATUSES)})$")


class ExperienceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    title: str
    category: str
    description: str | None
    wilaya_id: int
    meeting_point: str | None
    meeting_point_lat: float | None
    meeting_point_lng: float | None
    price_dzd: float | None
    duration_hours: float | None
    max_participants: int | None
    language: str | None
    included: list[str] | None
    what_to_bring: list[str] | None
    photos: list[str] | None
    status: str
    created_at: datetime
    updated_at: datetime | None


class ExperienceFeed(BaseModel):
    items: list[ExperienceRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool


class ExperienceDetail(BaseModel):
    """Experience + provider info for the detail view."""

    experience: ExperienceRead
    provider_name: str | None
    provider_avatar: str | None
    provider_role: str | None
