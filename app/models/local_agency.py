from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class LocalAgency(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "local_agencies"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    license_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    wilaya_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("wilayas.id"), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    is_verified: Mapped[bool] = mapped_column(default=False)
