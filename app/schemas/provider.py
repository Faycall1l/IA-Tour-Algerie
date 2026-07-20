import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.provider_profile import PROPERTY_TYPES, PROVIDER_TYPES


class ProviderRegisterRequest(BaseModel):
    phone: str = Field(..., min_length=8, max_length=20)
    provider_type: str = Field(..., pattern=f"^({'|'.join(PROVIDER_TYPES)})$")
    company_name: str | None = Field(None, max_length=200)
    property_name: str | None = Field(None, max_length=200)
    property_type: str | None = Field(None, pattern=f"^({'|'.join(PROPERTY_TYPES)})$")
    website: str | None = Field(None, max_length=500)
    experience_years: int | None = Field(None, ge=0, le=70)
    team_size: int | None = Field(None, ge=1, le=1000)


class ProviderRegisterResponse(BaseModel):
    user_id: uuid.UUID
    profile_id: uuid.UUID
    phone: str
    provider_type: str
    company_name: str | None = None
    property_name: str | None = None
    website: str | None = None
