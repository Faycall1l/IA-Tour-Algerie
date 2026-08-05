import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import USER_ROLES


class AdminActionResponse(BaseModel):
    message: str


class UserAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    role: str
    language: str
    is_active: bool
    is_verified: bool
    display_name: str | None
    avatar_url: str | None
    created_at: datetime


class UserAdminFeed(BaseModel):
    items: list[UserAdminRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool


class AdminRoleUpdate(BaseModel):
    role: str = Field(..., pattern=f"^({'|'.join(USER_ROLES)})$")


class ProviderProfileAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    provider_type: str
    is_verified: bool | None = None
    company_name: str | None
    property_name: str | None
    experience_years: int | None


class ProviderAdminFeed(BaseModel):
    items: list[ProviderProfileAdminRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool


class WilayaCount(BaseModel):
    wilaya_id: int
    count: int


class CategoryCount(BaseModel):
    category: str
    count: int


class StatsDashboard(BaseModel):
    total_pois: int
    total_stays: int
    total_experiences: int
    total_events: int
    total_users: int
    total_trips: int
    pois_per_wilaya: list[WilayaCount]
    pois_per_category: list[CategoryCount]
