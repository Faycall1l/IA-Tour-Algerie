import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin


class AgentSession(Base, TimestampMixin):
    """Tracks a multi-turn conversation session with an agent."""

    __tablename__ = "agent_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="travel_agent",
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    memories = relationship(
        "AgentMemory", back_populates="session",
        cascade="all, delete-orphan",
        order_by="AgentMemory.turn_index",
    )


class AgentMemory(Base, TimestampMixin):
    """Stores episodic turns and semantic facts for agent conversations.

    Two memory types:
    - 'episodic': raw conversation turns (user/assistant messages)
    - 'semantic': extracted facts (key-value pairs the agent explicitly stored)
    """

    __tablename__ = "agent_memories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    memory_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="episodic",
    )
    role: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
    )
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict)
    turn_index: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )

    # Semantic memory fields
    key: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True,
    )
    value: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    session: Mapped["AgentSession"] = relationship(back_populates="memories")
