import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Roles a user may self-assign. Deliberately excludes "admin" and "artisan":
# admin is never self-granted (privilege escalation), and artisan has no
# self-service onboarding flow yet.
SELF_ASSIGNABLE_ROLES = ("traveler", "guide", "agency", "hotel")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    role: str
    language: str
    is_active: bool
    is_verified: bool
    display_name: str | None
    avatar_url: str | None
    languages: list[str] | None
    bio: str | None
    created_at: datetime


class UserProfileRead(BaseModel):
    """Persistent traveler profile (cross-session agent context)."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    budget_level: str | None
    interests: list[str] | None
    home_wilaya_id: int | None
    home_wilaya_name: str | None = None
    travel_style: str | None
    preferred_language: str | None
    notes: str | None
    updated_at: datetime | None


class UserProfileUpdate(BaseModel):
    budget_level: str | None = Field(
        None, pattern=r"^(budget|mid-range|luxury)$", description="Per-trip budget level"
    )
    interests: list[str] | None = Field(
        None,
        max_length=6,
        description="Travel interests (beach, history, nature, food, culture, adventure, relax, family)",  # noqa: E501
    )
    home_wilaya_id: int | None = Field(None, ge=1, le=69)
    travel_style: str | None = Field(
        None,
        pattern=r"^(adventure|cultural|relax|family|food|nature|solo|business)$",
        description="Dominant travel style",
    )
    preferred_language: str | None = Field(None, min_length=2, max_length=5)
    notes: str | None = Field(None, max_length=2000)


class UserCreate(BaseModel):
    phone: str


class UserUpdate(BaseModel):
    display_name: str | None = Field(None, max_length=100)
    avatar_url: str | None = Field(None, max_length=500)
    languages: list[str] | None = None
    bio: str | None = Field(None, max_length=1000)


class RoleUpdate(BaseModel):
    role: str = Field(..., pattern=f"^({'|'.join(SELF_ASSIGNABLE_ROLES)})$")


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead
