import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class CircuitItemRead(BaseModel):
    id: uuid.UUID
    day_number: int
    item_order: int = 0
    time_slot: str | None
    item_type: str
    item_match_name: str | None
    notes: str | None

    model_config = {"from_attributes": True}


class CircuitRead(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None
    duration_days: int
    wilaya_id: int | None
    category: str
    difficulty: str
    total_budget_est_dzd: float | None
    photo_url: str | None
    is_active: bool = True
    items: list[CircuitItemRead] = []

    model_config = {"from_attributes": True}


class CircuitFeed(BaseModel):
    items: list[CircuitRead]
    total: int
