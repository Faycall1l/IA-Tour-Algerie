from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin, UUIDPkMixin

DISCUSSION_ENTITY_TYPES = ("poi", "experience", "stay")


class DiscussionThread(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "discussion_threads"

    __table_args__ = (
        Index("ix_discussion_threads_entity", "entity_type", "entity_id"),
        Index("ix_discussion_threads_created_by", "created_by"),
        CheckConstraint(
            f"entity_type IN {DISCUSSION_ENTITY_TYPES}",
            name="ck_thread_entity_type",
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )


class DiscussionPost(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "discussion_posts"

    __table_args__ = (
        Index("ix_discussion_posts_thread", "thread_id"),
        Index("ix_discussion_posts_author", "author_id"),
    )

    thread_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discussion_threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("discussion_posts.id", ondelete="SET NULL"),
        nullable=True,
    )
    author_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
