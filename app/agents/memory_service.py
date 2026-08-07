"""Agent memory service — persistent conversation memory for multi-turn agents.

Three memory tiers:
1. Working context: current conversation, passed as message_history
2. Episodic memory: stored conversation turns (reconstructed for multi-turn)
3. Semantic memory: extracted facts (key-value, agent-managed)

Uses PostgreSQL via SQLAlchemy. Designed for PydanticAI message_history injection.
"""

import logging
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_memory import AgentMemory, AgentSession

logger = logging.getLogger(__name__)

# Maximum turns to load for message_history (to avoid context overflow)
MAX_HISTORY_TURNS = 6

# Semantic memory caps — bound agent-controlled writes to prevent memory
# poisoning / storage abuse (a single key/value pair is not unbounded).
MAX_MEMORY_KEY_LEN = 64
MAX_MEMORY_VALUE_LEN = 2000
MAX_SEMANTIC_MEMORIES_PER_SESSION = 100


async def get_or_create_session(
    db: AsyncSession,
    user_id: UUID,
    session_id: UUID | None = None,
    agent_type: str = "travel_agent",
) -> AgentSession:
    """Get an existing session or create a new one.

    If session_id is provided and exists for this user, return it.
    Otherwise create a fresh session.
    """
    if session_id is not None:
        result = await db.execute(
            select(AgentSession).where(
                AgentSession.id == session_id,
                AgentSession.user_id == user_id,
                AgentSession.is_active.is_(True),
            )
        )
        session = result.scalar_one_or_none()
        if session:
            return session

    session = AgentSession(
        user_id=user_id,
        agent_type=agent_type,
        title=None,
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def load_message_history(
    db: AsyncSession,
    session_id: UUID,
    max_turns: int = MAX_HISTORY_TURNS,
) -> list[dict]:
    """Load recent episodic turns as a list of message dicts.

    Returns messages in chronological order, suitable for
    reconstructing PydanticAI message_history.

    Returns a list of dicts with keys: role, content, tool_calls (optional).
    """
    result = await db.execute(
        select(AgentMemory)
        .where(
            AgentMemory.session_id == session_id,
            AgentMemory.memory_type == "episodic",
        )
        .order_by(AgentMemory.turn_index.asc())
        .limit(max_turns * 2)  # Each turn = user + assistant
    )
    memories = result.scalars().all()

    messages = []
    for mem in memories:
        entry = {"role": mem.role, "content": mem.content}
        meta = mem.extra or {}
        if meta.get("tool_calls"):
            entry["tool_calls"] = meta["tool_calls"]
        if meta.get("tool_result"):
            entry["tool_result"] = meta["tool_result"]
        messages.append(entry)

    return messages


async def store_episodic_turn(
    db: AsyncSession,
    session_id: UUID,
    role: str,
    content: str,
    turn_index: int,
    extra: dict | None = None,
) -> AgentMemory:
    """Store a single conversation turn in episodic memory."""
    memory = AgentMemory(
        session_id=session_id,
        memory_type="episodic",
        role=role,
        content=content,
        extra=extra or {},
        turn_index=turn_index,
    )
    db.add(memory)
    await db.commit()
    return memory


async def store_agent_run(
    db: AsyncSession,
    session_id: UUID,
    user_message: str,
    assistant_reply: str,
    turn_index: int,
    tool_calls: list[str] | None = None,
) -> None:
    """Store a complete user→assistant turn pair."""
    await store_episodic_turn(
        db,
        session_id,
        "user",
        user_message,
        turn_index=turn_index,
    )
    await store_episodic_turn(
        db,
        session_id,
        "assistant",
        assistant_reply,
        turn_index=turn_index + 1,
        extra={"tool_calls": tool_calls} if tool_calls else {},
    )


async def remember(
    db: AsyncSession,
    session_id: UUID,
    key: str,
    value: str,
) -> AgentMemory:
    """Store a semantic fact about the user/trip.

    Overwrites previous value for the same key within the session.

    Raises ``ValueError`` if the key/value exceed length caps or the session
    already holds the maximum number of distinct semantic memories.
    """
    key = (key or "").strip()
    value = (value or "").strip()
    if not key:
        raise ValueError("Memory key must not be empty")
    if len(key) > MAX_MEMORY_KEY_LEN:
        raise ValueError(f"Memory key too long ({len(key)} > {MAX_MEMORY_KEY_LEN})")
    if len(value) > MAX_MEMORY_VALUE_LEN:
        raise ValueError(f"Memory value too long ({len(value)} > {MAX_MEMORY_VALUE_LEN})")

    # Remove previous value for this key
    existing = await db.execute(
        select(AgentMemory).where(
            AgentMemory.session_id == session_id,
            AgentMemory.memory_type == "semantic",
            AgentMemory.key == key,
        )
    )
    for old in existing.scalars().all():
        await db.delete(old)

    # Enforce a per-session cap on distinct semantic facts (after replacing,
    # so overwriting an existing key never trips the cap).
    count = await db.execute(
        select(func.count(AgentMemory.id)).where(
            AgentMemory.session_id == session_id,
            AgentMemory.memory_type == "semantic",
        )
    )
    if count.scalar_one() >= MAX_SEMANTIC_MEMORIES_PER_SESSION:
        raise ValueError(
            f"Memory limit reached ({MAX_SEMANTIC_MEMORIES_PER_SESSION} facts per session)"
        )

    memory = AgentMemory(
        session_id=session_id,
        memory_type="semantic",
        role="assistant",
        content=value,
        key=key,
        value=value,
        turn_index=0,
    )
    db.add(memory)
    await db.commit()
    await db.refresh(memory)
    return memory


async def recall(
    db: AsyncSession,
    session_id: UUID,
    key: str | None = None,
) -> list[dict]:
    """Retrieve semantic facts from a session.

    If key is provided, search by key (exact or ILIKE).
    If key is None, return all semantic memories.
    """
    query = select(AgentMemory).where(
        AgentMemory.session_id == session_id,
        AgentMemory.memory_type == "semantic",
    )
    if key:
        query = query.where(AgentMemory.key.ilike(f"%{key}%"))

    result = await db.execute(query.order_by(AgentMemory.created_at.desc()))
    memories = result.scalars().all()

    return [
        {"key": mem.key, "value": mem.value, "created_at": str(mem.created_at)}
        for mem in memories
        if mem.key and mem.value
    ]


async def get_next_turn_index(
    db: AsyncSession,
    session_id: UUID,
) -> int:
    """Get the next turn index for a session."""
    result = await db.execute(
        select(AgentMemory.turn_index)
        .where(
            AgentMemory.session_id == session_id,
            AgentMemory.memory_type == "episodic",
        )
        .order_by(AgentMemory.turn_index.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    return (last or 0) + 1


async def delete_session(
    db: AsyncSession,
    session_id: UUID,
    user_id: UUID,
) -> bool:
    """Soft-delete a session (set is_active=False)."""
    result = await db.execute(
        update(AgentSession)
        .where(
            AgentSession.id == session_id,
            AgentSession.user_id == user_id,
        )
        .values(is_active=False)
    )
    await db.commit()
    return result.rowcount > 0


async def get_user_sessions(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 20,
) -> list[AgentSession]:
    """Get all active sessions for a user."""
    result = await db.execute(
        select(AgentSession)
        .where(
            AgentSession.user_id == user_id,
            AgentSession.is_active.is_(True),
        )
        .order_by(AgentSession.updated_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def build_message_history(messages: list[dict]) -> str:
    """Build a compact context string from message history.

    Instead of reconstructing PydanticAI ModelMessage objects (which
    requires complex object reconstruction), we build a structured
    text preamble that injects previous conversation context into
    the system prompt.

    This avoids serialization issues with PydanticAI internal message types.
    """
    if not messages:
        return ""

    from app.agents.harness import sanitize_history

    messages = sanitize_history(messages)
    if not messages:
        return ""

    parts = ["\n\n--- PREVIOUS CONVERSATION ---"]
    for msg in messages:
        role = msg.get("role", "unknown").capitalize()
        content = msg.get("content", "")
        if content:
            parts.append(f"[{role}]: {content[:500]}")
    parts.append("--- END PREVIOUS CONVERSATION ---\n")
    return "\n".join(parts)
