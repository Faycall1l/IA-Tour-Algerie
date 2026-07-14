import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.price_report import TRANSPORT_MODES


class PriceReportCreate(BaseModel):
    origin_wilaya_id: int = Field(..., ge=1, le=999)
    dest_wilaya_id: int = Field(..., ge=1, le=999)
    transport_mode: str = Field(..., pattern=f"^({'|'.join(TRANSPORT_MODES)})$")
    price_dzd: float = Field(..., gt=0, le=1_000_000)


class PriceReportRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    origin_wilaya_id: int
    dest_wilaya_id: int
    transport_mode: str
    price_dzd: float
    confidence: str
    created_at: datetime


class PriceRange(BaseModel):
    min: float
    max: float
    median: float
    count: int


class PriceEstimateResponse(BaseModel):
    origin_wilaya_id: int
    origin_name: str
    dest_wilaya_id: int
    dest_name: str
    transport_mode: str
    range: PriceRange | None
    advice: str | None


class PriceReportFeed(BaseModel):
    items: list[PriceReportRead]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_prev: bool
    has_next: bool
