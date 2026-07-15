import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Collection ──

class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    is_public: bool = False


class CollectionUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    is_public: bool | None = None


# ── Collection Items ──

class CollectionItemCreate(BaseModel):
    entity_type: str = Field(..., pattern="^(poi|stay|experience)$")
    entity_id: uuid.UUID
    notes: str | None = Field(None, max_length=1000)
    sort_order: int = 0


class CollectionItemBatchCreate(BaseModel):
    items: list[CollectionItemCreate]


class CollectionItemRead(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    notes: str | None = None
    sort_order: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectionRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    description: str | None = None
    is_public: bool
    item_count: int = 0
    created_at: datetime
    updated_at: datetime | None = None
    items: list[CollectionItemRead] = []

    model_config = {"from_attributes": True}


class CollectionBrief(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    is_public: bool
    item_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectionFeed(BaseModel):
    items: list[CollectionBrief]
    total: int
