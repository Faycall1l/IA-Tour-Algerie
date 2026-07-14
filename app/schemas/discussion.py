import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.discussion import DISCUSSION_ENTITY_TYPES

ENTITY_PATTERN = f"^({'|'.join(DISCUSSION_ENTITY_TYPES)})$"


class DiscussionThreadCreate(BaseModel):
    entity_type: str = Field(..., pattern=ENTITY_PATTERN)
    entity_id: uuid.UUID
    title: str | None = Field(None, max_length=200)


class DiscussionPostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: uuid.UUID | None = None


class DiscussionPostRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    thread_id: uuid.UUID
    parent_id: uuid.UUID | None
    author_id: uuid.UUID
    author_name: str | None = None
    content: str
    created_at: datetime
    updated_at: datetime | None


class DiscussionThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    title: str | None
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime | None
    post_count: int = 0
    last_post_at: datetime | None = None


class DiscussionThreadDetail(BaseModel):
    thread: DiscussionThreadRead
    posts: list[DiscussionPostRead]


class DiscussionThreadFeed(BaseModel):
    items: list[DiscussionThreadRead]
    total: int
