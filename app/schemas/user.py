from pydantic import BaseModel, ConfigDict
import uuid
from datetime import datetime


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone: str
    role: str
    language: str
    is_active: bool
    display_name: str | None
    avatar_url: str | None
    created_at: datetime


class UserCreate(BaseModel):
    phone: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead
