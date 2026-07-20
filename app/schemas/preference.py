import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.preference import BUDGET_LEVELS, TRAVEL_STYLES

BUDGET_PATTERN = f"^({'|'.join(BUDGET_LEVELS)})$"
STYLE_PATTERN = f"^({'|'.join(TRAVEL_STYLES)})$"


class PreferenceUpdate(BaseModel):
    preferred_categories: list[str] | None = Field(None, max_length=20)
    budget_level: str | None = Field(None, pattern=BUDGET_PATTERN)
    travel_style: str | None = Field(None, pattern=STYLE_PATTERN)
    accessibility_needed: bool | None = None
    preferred_transport: list[str] | None = Field(None, max_length=10)
    max_travel_distance_km: int | None = Field(None, ge=1, le=10000)
    language: str | None = Field(None, min_length=2, max_length=5)
    interests: str | None = Field(None, max_length=2000)


class PreferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    preferred_categories: list[str] | None
    budget_level: str | None
    travel_style: str | None
    accessibility_needed: bool | None
    preferred_transport: list[str] | None
    max_travel_distance_km: int | None
    language: str | None
    interests: str | None
    created_at: datetime
    updated_at: datetime | None
