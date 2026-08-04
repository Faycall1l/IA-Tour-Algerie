"""Memory tools for agents — remember and recall facts across sessions.

These tools give the agent explicit control over semantic memory:
- 'remember' to store facts (user preferences, trip details, etc.)
- 'recall' to retrieve previously stored facts

Memory is scoped to the current session (conversation).
"""

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from app.agents.deps import TravelAgentDeps
from app.agents.memory_service import recall as _recall
from app.agents.memory_service import remember as _remember


class RememberParams(BaseModel):
    key: str = Field(
        ..., min_length=1, max_length=64,
        description="Fact label (e.g., 'user_budget', 'destination', 'dietary_pref')",
    )
    value: str = Field(
        ..., min_length=1, max_length=2000,
        description="Fact content to remember",
    )


class RememberOutput(BaseModel):
    status: str
    message: str


class RecallParams(BaseModel):
    key: str | None = Field(None, max_length=100, description="Fact key to search for. Omit to retrieve all stored facts.")


class RecallResult(BaseModel):
    key: str
    value: str


class RecallOutput(BaseModel):
    results: list[RecallResult]
    total: int


async def remember(ctx: RunContext[TravelAgentDeps], params: RememberParams) -> RememberOutput:
    """Store a fact in memory. Use this to remember user preferences, trip details,
    budget constraints, dietary restrictions, or any information the user shares
    that should be remembered for later turns.

    Facts are stored per-session and can be retrieved with 'recall'.
    """
    session_id = ctx.deps.session_id
    if not session_id:
        return RememberOutput(status="error", message="No active session")

    try:
        await _remember(ctx.deps.db, session_id, params.key, params.value)
    except ValueError as exc:
        return RememberOutput(status="error", message=str(exc))
    return RememberOutput(
        status="ok",
        message=f"Remembered: {params.key} = {params.value[:100]}",
    )


async def recall(ctx: RunContext[TravelAgentDeps], params: RecallParams) -> RecallOutput:
    """Retrieve stored facts from memory. Use this to recall user preferences,
    trip details, or any information that was previously stored.

    If no key is given, returns all stored facts for the current session.
    """
    session_id = ctx.deps.session_id
    if not session_id:
        return RecallOutput(results=[], total=0)

    results = await _recall(ctx.deps.db, session_id, key=params.key)
    return RecallOutput(
        results=[RecallResult(key=r["key"], value=r["value"]) for r in results],
        total=len(results),
    )
