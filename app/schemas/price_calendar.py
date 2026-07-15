import uuid
from datetime import date

from pydantic import BaseModel, Field


class PriceCalendarEntryCreate(BaseModel):
    date: date
    price_dzd: float = Field(..., ge=0, le=10_000_000)
    available_spots: int | None = Field(None, ge=0, le=1000)


class PriceCalendarBatchCreate(BaseModel):
    prices: list[PriceCalendarEntryCreate]


class PriceCalendarEntryRead(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    date: date
    price_dzd: float
    available_spots: int | None


class PriceCalendarRead(BaseModel):
    entity_id: uuid.UUID
    entity_type: str
    prices: list[PriceCalendarEntryRead]
    min_price: float
    max_price: float
    available_dates: int
