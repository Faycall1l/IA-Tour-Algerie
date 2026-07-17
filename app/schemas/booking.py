import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.booking import BOOKING_STATUSES


class BookingCreate(BaseModel):
    entity_type: str = Field("experience", pattern=r"^(experience|circuit)$")
    entity_id: uuid.UUID
    message: str | None = Field(None, max_length=2000)
    participants: int = Field(1, ge=1, le=100)
    requested_date: date | None = None


class BookingStatusUpdate(BaseModel):
    status: str = Field(..., pattern=f"^({'|'.join(BOOKING_STATUSES)})$")


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    traveler_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    status: str
    message: str | None
    participants: int
    requested_date: date | None
    created_at: datetime
    updated_at: datetime | None


class BookingDetail(BaseModel):
    booking: BookingRead
    traveler_name: str | None
    traveler_avatar: str | None
    booking_title: str | None
    provider_id: uuid.UUID | None
    provider_name: str | None
