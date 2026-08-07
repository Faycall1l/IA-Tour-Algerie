"""Agent dependencies — injected into every agent run via RunContext."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@dataclass
class TravelAgentDeps:
    """Dependencies injected into travel agent runs.

    Carries the authenticated user, database session, transport service,
    memory session ID, and any other context the agent tools need.
    Every tool receives this via RunContext.
    """

    user: User
    db: AsyncSession
    request_id: str | None = None
    session_id: UUID | None = None
    message_history: str = ""
    turn_index: int = 0

    @classmethod
    def create(cls, user: User, db: AsyncSession, request_id: str | None = None) -> TravelAgentDeps:
        return cls(user=user, db=db, request_id=request_id)
