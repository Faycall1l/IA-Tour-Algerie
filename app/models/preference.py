from sqlalchemy import ARRAY, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


TRAVEL_STYLES = ("solo", "couple", "family", "group", "business")
BUDGET_LEVELS = ("budget", "moderate", "premium", "luxury")


class UserPreference(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "user_preferences"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    preferred_categories: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True, comment="Preferred POI categories"
    )
    budget_level: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="budget/moderate/premium/luxury"
    )
    travel_style: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="solo/couple/family/group/business"
    )
    accessibility_needed: Mapped[bool | None] = mapped_column(nullable=True)
    preferred_transport: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(30)), nullable=True, comment="walking/public/car/bike/taxi"
    )
    max_travel_distance_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True, default="fr")
    interests: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Free-text interests for AI agents")
