import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    poi_id: uuid.UUID
    overall_score: float = Field(..., ge=1, le=5)
    text: str | None = Field(None, max_length=2000)


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    poi_id: uuid.UUID
    overall_score: float
    text: str | None
    is_verified: bool
    created_at: datetime


class ReviewFeed(BaseModel):
    items: list[ReviewRead]
    total: int
    page: int
    page_size: int


class POIRating(BaseModel):
    poi_id: uuid.UUID
    average_score: float
    total_reviews: int
    distribution: dict[int, int]
