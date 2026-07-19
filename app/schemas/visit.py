import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.visit import VISIT_ENTITY_TYPES


class VisitCreate(BaseModel):
    entity_type: str = Field(..., pattern=f"^({'|'.join(VISIT_ENTITY_TYPES)})$")
    entity_id: uuid.UUID


class VisitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    visited_at: datetime


class VisitFeed(BaseModel):
    items: list[VisitRead]
    total: int
