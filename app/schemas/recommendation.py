import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.recommendation import BUDGET_TIERS, TRAVEL_STYLES


class PreferenceUpdate(BaseModel):
    preferred_categories: list[str] | None = None
    preferred_wilayas: list[int] | None = None
    travel_style: str | None = Field(None, pattern=f"^({'|'.join(TRAVEL_STYLES)})$")
    budget_tier: str | None = Field(None, pattern=f"^({'|'.join(BUDGET_TIERS)})$")
    interests: list[str] | None = None
    avoided_categories: list[str] | None = None
    preferred_duration_min: int | None = Field(None, ge=10, le=480)


class PreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    preferred_categories: list[str] | None = None
    preferred_wilayas: list[int] | None = None
    travel_style: str | None = None
    budget_tier: str | None = None
    interests: list[str] | None = None
    avoided_categories: list[str] | None = None
    preferred_duration_min: int | None = None
    profile_summary: str | None = None
    interaction_score: dict | None = None
    created_at: datetime
    updated_at: datetime | None = None


class RecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    wilaya_id: int | None = None
    score: float
    explanation: str | None = None
    reason_code: str | None = None
    is_seen: bool = False
    created_at: datetime


class RecommendationFeedback(BaseModel):
    feedback: str = Field(..., pattern="^(liked|dismissed|bookmarked)$")


class RecommendationFeed(BaseModel):
    items: list[RecommendationRead]
    total: int
    model_version: str | None = None


class RecommendationRequest(BaseModel):
    wilaya_id: int | None = Field(None, ge=1, le=69)
    entity_type: str | None = Field(None, pattern="^(poi|experience|stay)$")
    limit: int = Field(20, ge=1, le=50)


class InteractionScore(BaseModel):
    category_scores: dict[str, float] = {}
    wilaya_scores: dict[int, float] = {}
    tag_scores: dict[str, float] = {}
    total_interactions: int = 0
    favorite_count: int = 0
    trip_count: int = 0
    collection_count: int = 0
    avg_duration_min: float | None = None
