"""Persistent traveler profile — cross-session preferences for the agent pipeline.

Unlike per-session ``agent_memories``, the traveler profile survives across
sessions: budget level, interests, and home wilaya are mined from conversation
turns and injected into every agent prompt, so multi-turn personalization
carries over when a user starts a new session or switches agents.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, CheckConstraint, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

BUDGET_LEVELS = ("budget", "mid-range", "luxury")
TRAVEL_STYLES = (
    "adventure",
    "cultural",
    "relax",
    "family",
    "food",
    "nature",
    "solo",
    "business",
)


class UserProfile(Base):
    """One-to-one traveler profile keyed by user id."""

    __tablename__ = "user_profiles"

    __table_args__ = (
        CheckConstraint(
            f"budget_level IS NULL OR budget_level IN {BUDGET_LEVELS}",
            name="ck_user_profile_budget",
        ),
        CheckConstraint(
            f"travel_style IS NULL OR travel_style IN {TRAVEL_STYLES}",
            name="ck_user_profile_travel_style",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    budget_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)), nullable=True)
    home_wilaya_id: Mapped[int | None] = mapped_column(
        ForeignKey("wilayas.id", ondelete="SET NULL"),
        nullable=True,
    )
    travel_style: Mapped[str | None] = mapped_column(String(20), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )
