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
