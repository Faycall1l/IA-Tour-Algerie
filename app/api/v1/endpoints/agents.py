"""Pydantic AI agent endpoints for travel planning.

Five agents are available:
- `/chat` — general travel assistant (20 req/hour)
- `/plan-trip` — structured itinerary planner (10 req/hour)
- `/search` — unified POI/stay/experience search (30 req/hour)
- `/transport` — transport specialist: routes, schedules, contacts (20 req/hour)
- `/events` — events & festivals specialist (20 req/hour)
- `/sessions` — list/clear agent conversation sessions

All require JWT auth. Supports multi-turn memory via session_id.
Returns 503 if no API key is configured.
Every call is traced via the observability system for P1 monitoring.
"""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import TravelAgentDeps
from app.agents.harness import detect_injection, sanitize_input, validate_input
from app.agents.memory_service import (
    build_message_history,
    delete_session,
    get_or_create_session,
    get_next_turn_index,
    get_user_sessions,
    load_message_history,
    store_agent_run,
)
from app.agents.observability import Trace, trace_store
from app.api import deps
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agents"])
limiter = Limiter(key_func=get_remote_address)


# ── Request schemas ──

class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User's travel question")
    wilaya_id: int | None = Field(None, ge=1, le=58)
    session_id: str | None = Field(None, description="Resume an existing conversation session")


class PlanTripRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=100)
    duration_days: int = Field(..., ge=1, le=30)
    budget: str = Field("mid-range", pattern=r"^(budget|mid-range|luxury)$")
    interests: str = Field("", max_length=500, description="Comma-separated interests")
    session_id: str | None = Field(None, description="Resume an existing conversation session")


class AgentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    wilaya_id: int | None = None
    session_id: str | None = Field(None, description="Resume an existing conversation session")


class TransportQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Transport question")
    from_wilaya: int | None = Field(None, ge=1, le=58)
    to_wilaya: int | None = Field(None, ge=1, le=58)
    session_id: str | None = Field(None, description="Resume an existing conversation session")


class EventsQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Events/festivals question")
    wilaya_id: int | None = Field(None, ge=1, le=58)
    session_id: str | None = Field(None, description="Resume an existing conversation session")


# ── Response schemas ──

class AgentChatResponse(BaseModel):
    reply: str
    session_id: str | None = None
    sources: list[dict] = Field(default_factory=list)


class TripPlanResponse(BaseModel):
    plan: str
    session_id: str | None = None


class AgentSearchResponse(BaseModel):
    reply: str = ""
    session_id: str | None = None
    results: list[dict] = Field(default_factory=list)
    total: int = 0


class SessionListItem(BaseModel):
    id: str
    agent_type: str
    title: str | None = None
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    sessions: list[SessionListItem]


# ── Trace helper ──

async def _run_agent_traced(
    agent, message: str, agent_deps: TravelAgentDeps, agent_name: str,
) -> str:
    """Run an agent with full observability tracing, input validation, PII redaction,
    and multi-turn memory (load history before, store after).
    """
    trace = Trace(
        trace_id=uuid.uuid4().hex,
        agent_name=agent_name,
        user_id=str(agent_deps.user.id),
        start_time=time.time(),
    )

    # Input validation
    is_valid, error = validate_input(message)
    if not is_valid:
        trace.finish(success=False, error=error)
        trace_store.record(trace)
        raise HTTPException(status_code=400, detail=error)

    # PII redaction
    sanitized = sanitize_input(message)

    try:
        result = await agent.run(sanitized, deps=agent_deps)
        output = str(result.output)
        trace.output_tokens = len(output) // 4
        trace.finish(success=True)
    except HTTPException:
        raise
    except Exception as e:
        trace.finish(success=False, error=str(e)[:500])
        trace_store.record(trace)
        logger.error("Agent %s failed: %s", agent_name, e)
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    # Store this turn in memory (if session available)
    if agent_deps.session_id and agent_deps.db:
        try:
            await store_agent_run(
                agent_deps.db, agent_deps.session_id,
                user_message=message,
                assistant_reply=output,
                turn_index=agent_deps.turn_index,
            )
        except Exception as e:
            logger.warning("Failed to store agent memory turn: %s", e)

    trace_store.record(trace)
    return output


# ── Dependency: extract agent from app.state ──

def _get_agent(request: Request, name: str):
    """Get an agent from app.state with graceful fallback."""
    agent = getattr(request.app.state, name, None)
    if agent is None:
        raise HTTPException(
            status_code=503,
            detail="Agents are not available — configure AGENT__VLLM settings in .env",
        )
    return agent


# ── Memory deps builder ──

async def _make_memory_deps(
    current_user: User,
    db: AsyncSession,
    request: Request,
    session_id: str | None = None,
    agent_type: str = "travel_agent",
) -> TravelAgentDeps:
    """Build TravelAgentDeps with memory context.

    Creates or resumes a session, loads message history, and sets up
    turn tracking so the agent has multi-turn conversation memory.
    """
    parsed_session_id = None
    if session_id:
        try:
            parsed_session_id = uuid.UUID(session_id)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid session_id: {session_id}",
            )

    session = await get_or_create_session(
        db, current_user.id,
        session_id=parsed_session_id,
        agent_type=agent_type,
    )
    history = await load_message_history(db, session.id)
    history_text = build_message_history(history)
    next_turn = await get_next_turn_index(db, session.id)

    return TravelAgentDeps(
        user=current_user,
        db=db,
        request_id=str(request.headers.get("x-request-id", "")),
        session_id=session.id,
        message_history=history_text,
        turn_index=next_turn,
    )


# ── Endpoints ──


@router.post("/chat", response_model=AgentChatResponse)
@limiter.limit("20/hour")
async def agent_chat(
    body: AgentChatRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask the travel assistant any Algeria travel question."""
    agent = _get_agent(request, "travel_agent")
    agent_deps = await _make_memory_deps(
        current_user, db, request, body.session_id, "travel_agent",
    )
    reply = await _run_agent_traced(agent, body.message, agent_deps, "travel_agent")
    return AgentChatResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
    )


@router.post("/plan-trip", response_model=TripPlanResponse)
@limiter.limit("10/hour")
async def agent_plan_trip(
    body: PlanTripRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a detailed itinerary for an Algeria trip."""
    agent = _get_agent(request, "itinerary_agent")
    agent_deps = await _make_memory_deps(
        current_user, db, request, body.session_id, "itinerary_agent",
    )
    prompt = (
        f"Plan a {body.duration_days}-day trip to {body.destination} "
        f"on a {body.budget} budget."
    )
    if body.interests.strip():
        prompt += f"\nInterests: {body.interests}"
    reply = await _run_agent_traced(agent, prompt, agent_deps, "itinerary_agent")
    return TripPlanResponse(
        plan=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
    )


@router.post("/search", response_model=AgentSearchResponse)
@limiter.limit("30/hour")
async def agent_search(
    body: AgentSearchRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified search across POIs, stays, and experiences via agent."""
    agent = _get_agent(request, "search_agent")
    agent_deps = await _make_memory_deps(
        current_user, db, request, body.session_id, "search_agent",
    )
    reply = await _run_agent_traced(agent, body.query, agent_deps, "search_agent")
    return AgentSearchResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
    )


@router.post("/transport", response_model=AgentChatResponse)
@limiter.limit("20/hour")
async def agent_transport(
    body: TransportQueryRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask the transport specialist about routes, schedules, or contacts."""
    agent = _get_agent(request, "transport_agent")
    agent_deps = await _make_memory_deps(
        current_user, db, request, body.session_id, "transport_agent",
    )
    reply = await _run_agent_traced(agent, body.query, agent_deps, "transport_agent")
    return AgentChatResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
    )


@router.post("/events", response_model=AgentChatResponse)
@limiter.limit("20/hour")
async def agent_events(
    body: EventsQueryRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask the events specialist about festivals and cultural activities."""
    agent = _get_agent(request, "events_agent")
    agent_deps = await _make_memory_deps(
        current_user, db, request, body.session_id, "events_agent",
    )
    reply = await _run_agent_traced(agent, body.query, agent_deps, "events_agent")
    return AgentChatResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
    )


# ── Session management ──

@router.get("/sessions", response_model=SessionListResponse)
@limiter.limit("30/hour")
async def list_sessions(
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all active agent conversation sessions for the current user."""
    sessions = await get_user_sessions(db, current_user.id)
    return SessionListResponse(
        sessions=[
            SessionListItem(
                id=str(s.id),
                agent_type=s.agent_type,
                title=s.title,
                created_at=str(s.created_at),
                updated_at=str(s.updated_at),
            )
            for s in sessions
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
@limiter.limit("20/hour")
async def clear_session(
    session_id: str,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent conversation session.
    
    This soft-deletes the session and all its memories.
    """
    try:
        parsed = uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid session_id: {session_id}")
    
    deleted = await delete_session(db, parsed, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
