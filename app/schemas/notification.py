import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: str | None
    reference_type: str | None
    reference_id: uuid.UUID | None
    is_read: bool
    created_at: datetime


class NotificationFeed(BaseModel):
    items: list[NotificationRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
    unread_count: int
