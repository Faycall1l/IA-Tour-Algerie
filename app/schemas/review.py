import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SubRatings(BaseModel):
    """Category-specific sub-rating fields (TripAdvisor-style breakdown)."""
    model_config = ConfigDict(extra="allow")


class ReviewCreate(BaseModel):
    poi_id: uuid.UUID
    overall_score: float = Field(..., ge=1, le=5)
    text: str | None = Field(None, max_length=2000)
    sub_ratings: SubRatings | None = None


class ReviewUpdate(BaseModel):
    overall_score: float | None = Field(None, ge=1, le=5)
    text: str | None = Field(None, max_length=2000)
    sub_ratings: SubRatings | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    poi_id: uuid.UUID
    overall_score: float
    text: str | None
    is_verified: bool
    sub_ratings: SubRatings | None = None
    helpfulness_count: int = 0
    owner_response: str | None = None
    response_created_at: datetime | None = None
    edited_at: datetime | None = None
    created_at: datetime


class ReviewFeed(BaseModel):
    items: list[ReviewRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool


class POIRating(BaseModel):
    poi_id: uuid.UUID
    average_score: float
    total_reviews: int
    distribution: dict[int, int]


class ReviewVoteCreate(BaseModel):
    helpful: bool


class ReviewVoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    review_id: uuid.UUID
    helpful: bool
    created_at: datetime


class OwnerResponseCreate(BaseModel):
    response: str = Field(..., min_length=1, max_length=2000)
