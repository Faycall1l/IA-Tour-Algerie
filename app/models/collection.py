import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin


class Collection(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "collections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    items: Mapped[list["CollectionItem"]] = relationship(
        "CollectionItem", back_populates="collection", cascade="all, delete-orphan", lazy="selectin"
    )


class CollectionItem(UUIDPkMixin, Base):
    __tablename__ = "collection_items"

    __table_args__ = (
        UniqueConstraint("collection_id", "entity_type", "entity_id", name="uq_collection_item"),
        CheckConstraint("entity_type IN ('poi', 'stay', 'experience')", name="ck_ci_entity_type"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False,
        default=datetime.utcnow,
    )

    collection: Mapped["Collection"] = relationship("Collection", back_populates="items")
