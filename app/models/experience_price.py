from datetime import date as date_type

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import UUIDPkMixin


class ExperiencePrice(UUIDPkMixin, Base):
    __tablename__ = "experience_prices"

    __table_args__ = (
        UniqueConstraint("experience_id", "date", name="uq_experience_price_date"),
        Index("ix_experience_prices_experience", "experience_id"),
        Index("ix_experience_prices_date", "date"),
    )

    experience_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("experiences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    price_dzd: Mapped[float] = mapped_column(Float, nullable=False)
    available_spots: Mapped[int | None] = mapped_column(Integer, nullable=True)
