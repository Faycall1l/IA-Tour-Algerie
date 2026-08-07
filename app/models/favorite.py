import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

FAVORITE_ENTITY_TYPES = ("poi", "experience", "stay")


class Favorite(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "favorites"

    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_id", name="uq_favorites_user_entity"),
        Index("ix_favorites_user", "user_id"),
        Index("ix_favorites_entity", "entity_type", "entity_id"),
        CheckConstraint(
            f"entity_type IN {FAVORITE_ENTITY_TYPES}",
            name="ck_favorite_entity_type",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
