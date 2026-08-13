import uuid

from sqlalchemy import ARRAY, CheckConstraint, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import UUIDPkMixin

PROVIDER_TYPES = ("guide", "agency", "hotel")
PROPERTY_TYPES = ("hotel", "riad", "guesthouse", "hostel", "eco_lodge")


class ProviderProfile(UUIDPkMixin, Base):
    __tablename__ = "provider_profiles"

    __table_args__ = (
        CheckConstraint(f"provider_type IN {PROVIDER_TYPES}", name="ck_profile_provider_type"),
        CheckConstraint(
            f"property_type IS NULL OR property_type IN {PROPERTY_TYPES}",
            name="ck_profile_property_type",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    provider_type: Mapped[str] = mapped_column(String(20), nullable=False)

    user = relationship("User", backref=backref("profile", uselist=False), lazy="joined")

    is_verified: Mapped[bool] = mapped_column(default=False)

    # Guide-specific
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    specializations: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    max_group_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    certifications: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)

    # Agency-specific
    company_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    service_areas: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    team_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Hotel-specific
    property_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    property_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    amenities: Mapped[list[str] | None] = mapped_column(ARRAY(String(100)), nullable=True)
    price_range_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_range_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_in_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    check_out_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    star_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
