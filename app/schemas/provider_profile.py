import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.provider_profile import PROPERTY_TYPES


class ProviderProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    provider_type: str
    is_verified: bool

    experience_years: int | None
    specializations: list[str] | None
    max_group_size: int | None
    certifications: list[str] | None

    company_name: str | None
    registration_number: str | None
    service_areas: list[str] | None
    website: str | None
    team_size: int | None

    property_name: str | None
    property_type: str | None
    amenities: list[str] | None
    price_range_min: float | None
    price_range_max: float | None
    check_in_time: str | None
    check_out_time: str | None
    star_rating: int | None


class ProviderProfileUpdate(BaseModel):
    experience_years: int | None = Field(None, ge=0, le=100)
    specializations: list[str] | None = None
    max_group_size: int | None = Field(None, ge=1, le=100)
    certifications: list[str] | None = None
    company_name: str | None = Field(None, max_length=200)
    registration_number: str | None = Field(None, max_length=100)
    service_areas: list[str] | None = None
    website: str | None = Field(None, max_length=500)
    team_size: int | None = Field(None, ge=1, le=10000)
    property_name: str | None = Field(None, max_length=200)
    property_type: str | None = Field(None, pattern=f"^({'|'.join(PROPERTY_TYPES)})$")
    amenities: list[str] | None = None
    price_range_min: float | None = Field(None, ge=0, le=10_000_000)
    price_range_max: float | None = Field(None, ge=0, le=10_000_000)
    check_in_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    check_out_time: str | None = Field(None, pattern=r"^\d{2}:\d{2}$")
    star_rating: int | None = Field(None, ge=1, le=7)


class ProviderUserRead(BaseModel):
    """Public view of a provider — safe to expose to travelers."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    display_name: str | None
    avatar_url: str | None
    languages: list[str] | None
    bio: str | None
    role: str
    is_verified: bool
    profile: ProviderProfileRead | None
