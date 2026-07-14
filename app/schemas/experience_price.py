import uuid
from datetime import date

from pydantic import BaseModel, Field


class ExperiencePriceCreate(BaseModel):
    date: date
    price_dzd: float = Field(..., ge=0, le=10_000_000)
    available_spots: int | None = Field(None, ge=0, le=1000)


class ExperiencePriceBatchCreate(BaseModel):
    prices: list[ExperiencePriceCreate]


class ExperiencePriceRead(BaseModel):
    id: uuid.UUID
    experience_id: uuid.UUID
    date: date
    price_dzd: float
    available_spots: int | None


class ExperiencePriceCalendar(BaseModel):
    experience_id: uuid.UUID
    prices: list[ExperiencePriceRead]
    min_price: float
    max_price: float
    available_dates: int
