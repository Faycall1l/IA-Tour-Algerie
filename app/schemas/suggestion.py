import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.suggestion import SUGGESTION_FIELDS


class SuggestionCreate(BaseModel):
    entity_type: str = Field(..., pattern="^(poi|stay|experience)$")
    entity_id: uuid.UUID = Field(...)
    field_name: str = Field(..., pattern=f"^({'|'.join(SUGGESTION_FIELDS)})$")
    new_value: str = Field(..., min_length=1, max_length=2000)


class SuggestionReview(BaseModel):
    status: str = Field(..., pattern="^(approved|rejected)$")
    review_notes: str | None = Field(None, max_length=1000)


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID
    field_name: str
    old_value: str | None
    new_value: str
    status: str
    review_notes: str | None
    created_at: datetime
    updated_at: datetime | None


class SuggestionFeed(BaseModel):
    items: list[SuggestionRead]
    total: int
    page: int
    page_size: int
    total_pages: int
