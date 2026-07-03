import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LivePostCreate(BaseModel):
    caption: str | None = Field(None, max_length=500)
    wilaya_id: int | None = None
    poi_id: str | None = None


class LivePostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    photo_url: str
    caption: str | None
    wilaya_id: int | None
    poi_id: uuid.UUID | None
    is_moderated: bool
    created_at: datetime


class LivePostFeed(BaseModel):
    items: list[LivePostRead]
    total: int
    page: int
    page_size: int
