import uuid

from sqlalchemy import String, Text, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base
from app.db.mixins import UUIDPkMixin, TimestampMixin


class LivePost(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "live_posts"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    wilaya_id: Mapped[int | None] = mapped_column(
        ForeignKey("wilayas.id"), nullable=True, index=True
    )
    poi_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pois.id"), nullable=True
    )
    is_moderated: Mapped[bool] = mapped_column(Boolean, default=False)
