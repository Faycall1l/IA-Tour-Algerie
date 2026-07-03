import uuid

from sqlalchemy import String, LargeBinary, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from app.db.mixins import UUIDPkMixin, TimestampMixin


class AtharTravelerProfile(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "athar_traveler_profile"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    passport_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    encrypted_identity: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    assigned_agency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("local_agencies.id"), nullable=True
    )
    language_preference: Mapped[str] = mapped_column(String(10), default="fr")
    anonymous_geo_trail: Mapped[dict | None] = mapped_column(JSON, default=list)
