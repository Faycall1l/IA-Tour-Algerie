import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.event import EVENT_CATEGORIES


class EventCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    wilaya_id: int = Field(..., ge=1, le=58)
    category: str = Field(..., pattern=f"^({'|'.join(EVENT_CATEGORIES)})$")
    description: str | None = Field(None, max_length=2000)
    month: int = Field(..., ge=1, le=12)
    duration_days: int | None = Field(None, ge=1, le=31)
    is_recurring: bool | None = True
    photo_url: str | None = Field(None, max_length=500)


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    category: str | None = Field(None, pattern=f"^({'|'.join(EVENT_CATEGORIES)})$")
    description: str | None = Field(None, max_length=2000)
    month: int | None = Field(None, ge=1, le=12)
    duration_days: int | None = Field(None, ge=1, le=31)
    is_recurring: bool | None = None
    photo_url: str | None = Field(None, max_length=500)


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    wilaya_id: int
    category: str
    description: str | None
    month: int = Field(..., ge=1, le=12)
    duration_days: int | None
    is_recurring: bool | None
    photo_url: str | None
    created_at: datetime
    updated_at: datetime | None


class EventFeed(BaseModel):
    items: list[EventRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
