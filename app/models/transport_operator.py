import uuid
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class TransportOperator(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "transport_operators"
    __allow_unmapped__ = True

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name_ar: Mapped[str | None] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30))
    website: Mapped[str | None] = mapped_column(String(300))
    email: Mapped[str | None] = mapped_column(String(200))
    headquarters_wilaya_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("wilayas.id")
    )
    description: Mapped[str | None] = mapped_column(String(500))
    coverage_type: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON)
