from sqlalchemy import ARRAY, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

USER_ROLES = ("traveler", "guide", "agency", "hotel", "admin")


class User(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), default="traveler")
    language: Mapped[str] = mapped_column(String(5), default="fr")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    languages: Mapped[list[str] | None] = mapped_column(ARRAY(String(20)), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(1000), nullable=True)
