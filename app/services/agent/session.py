from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    db_session: AsyncSession | None = None
    user_id: str = ""
    trip_id: str = ""
    locale: str = "en"


_tool_ctx: ContextVar[ToolContext | None] = ContextVar("_tool_ctx", default=None)


def get_tool_context() -> ToolContext:
    val = _tool_ctx.get()
    if val is None:
        return ToolContext()
    return val


def set_tool_context(ctx: ToolContext) -> None:
    _tool_ctx.set(ctx)


@dataclass
class AgentContext(ToolContext):
    thread_id: str = ""


class UserSession:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        self.intent: dict[str, Any] = {}
        self.recent_interactions: list[str] = []
        self.locale: str = "en"

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "intent": self.intent,
            "recent_interactions": self.recent_interactions[-20:],
            "locale": self.locale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserSession:
        session = cls(data.get("user_id", ""))
        session.intent = data.get("intent", {})
        session.recent_interactions = data.get("recent_interactions", [])
        session.locale = data.get("locale", "en")
        return session


class SessionStore:
    def __init__(self) -> None:
        self._store: dict[str, UserSession] = {}
        self._redis_available = False
        self._init_redis()

    def _init_redis(self) -> None:
        try:
            import redis.asyncio as aioredis  # noqa: F401

            self._redis_available = True
        except ImportError:
            self._redis_available = False

    async def get(self, user_id: str) -> UserSession:
        if user_id in self._store:
            return self._store[user_id]
        session = UserSession(user_id)
        self._store[user_id] = session
        return session

    async def save(self, session: UserSession) -> None:
        self._store[session.user_id] = session


session_store = SessionStore()
