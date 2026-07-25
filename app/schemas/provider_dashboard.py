"""Provider dashboard schema."""
import uuid

from pydantic import BaseModel


class DashboardExperienceSummary(BaseModel):
    id: uuid.UUID
    title: str
    category: str
    wilaya_id: int
    status: str
    price_dzd: float | None
    photo_count: int = 0


class DashboardStaySummary(BaseModel):
    id: uuid.UUID
    name: str
    property_type: str
    wilaya_id: int
    is_active: bool
    price_per_night_dzd: float | None


class ProviderDashboard(BaseModel):
    provider_type: str
    company_name: str | None = None
    is_verified: bool = False

    total_experiences: int = 0
    active_experiences: int = 0
    total_stays: int = 0
    active_stays: int = 0

    top_experiences: list[DashboardExperienceSummary] = []
    top_stays: list[DashboardStaySummary] = []
