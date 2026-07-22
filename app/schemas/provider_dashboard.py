"""Provider dashboard schema."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class DashboardExperienceSummary(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    wilaya_id: int
    status: str
    price_dzd: float | None
    booking_count: int = 0
    avg_score: float | None = None
    review_count: int = 0
    photo_count: int = 0


class DashboardStaySummary(BaseModel):
    id: uuid.UUID
    name: str
    property_type: str
    wilaya_id: int
    is_active: bool
    price_per_night_dzd: float | None
    booking_count: int = 0
    avg_score: float | None = None
    review_count: int = 0


class DashboardBookingSummary(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    entity_title: str
    traveler_name: str
    status: str
    participants: int
    requested_date: str | None
    created_at: datetime


class DashboardReviewSummary(BaseModel):
    id: uuid.UUID
    entity_type: str
    entity_title: str
    reviewer_name: str
    overall_score: float
    text: str | None
    has_response: bool
    created_at: datetime


class ProviderDashboard(BaseModel):
    provider_type: str
    company_name: str | None = None
    is_verified: bool = False

    total_experiences: int = 0
    active_experiences: int = 0
    total_stays: int = 0
    active_stays: int = 0

    total_bookings: int = 0
    pending_bookings: int = 0
    confirmed_bookings: int = 0
    completed_bookings: int = 0

    total_reviews: int = 0
    average_score: float | None = None
    unresponded_reviews: int = 0

    recent_bookings: list[DashboardBookingSummary] = []
    recent_reviews: list[DashboardReviewSummary] = []
    top_experiences: list[DashboardExperienceSummary] = []
    top_stays: list[DashboardStaySummary] = []
