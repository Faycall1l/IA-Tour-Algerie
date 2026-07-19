import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.favorite import FAVORITE_ENTITY_TYPES


class FavoriteCreate(BaseModel):
    entity_type: str = Field(..., pattern=f"^({'|'.join(FAVORITE_ENTITY_TYPES)})$")
    entity_id: uuid.UUID


class FavoriteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    created_at: datetime


class FavoriteFeed(BaseModel):
    items: list[FavoriteRead]
    total: int
