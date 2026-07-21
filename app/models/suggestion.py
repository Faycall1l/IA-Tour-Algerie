from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

SUGGESTION_STATUSES = ("pending", "approved", "rejected")
SUGGESTION_FIELDS = ("phone", "website", "opening_hours", "description", "name", "category")


class Suggestion(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "suggestions"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="poi / stay / experience"
    )
    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Field being suggested (phone, website, etc.)"
    )
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
