import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
