"""Pydantic AI agent endpoints for travel planning.

Five agents are available:
- `/chat` — general travel assistant (20 req/hour)
- `/plan-trip` — structured itinerary planner (10 req/hour)
- `/search` — unified POI/stay/experience search (30 req/hour)
- `/transport` — transport specialist: routes, schedules, contacts (20 req/hour)
- `/events` — events & festivals specialist (20 req/hour)
- `/sessions` — list/clear agent conversation sessions

All require JWT auth. Supports multi-turn memory via session_id.
Returns 503 when the LLM backend is unavailable and the query cannot be
answered by the offline rule-based fallback (see ``app.agents.fallback``);
fallback replies carry ``degraded: true`` and an ``X-Agent-Degraded`` header.
Every call is traced via the observability system for P1 monitoring.
"""

import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import TravelAgentDeps
from app.agents.fallback import attempt_fallback_with_links
from app.agents.harness import sanitize_input, validate_input
from app.agents.links import AgentLink, render_links_section
from app.agents.memory_service import (
    build_message_history,
    delete_session,
    get_next_turn_index,
    get_or_create_session,
    get_user_sessions,
    load_message_history,
    store_agent_run,
)
from app.agents.observability import Trace, trace_store
from app.agents.resilience import AgentUnavailable, run_agent_safely
from app.api import deps
from app.db.session import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agents"])
limiter = Limiter(key_func=get_remote_address)


# ── Request schemas ──


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="User's travel question")
    wilaya_id: int | None = Field(None, ge=1, le=69)
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
    from_wilaya: int | None = Field(None, ge=1, le=69)
    to_wilaya: int | None = Field(None, ge=1, le=69)
    session_id: str | None = Field(None, description="Resume an existing conversation session")


class EventsQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Events/festivals question")
    wilaya_id: int | None = Field(None, ge=1, le=69)
    session_id: str | None = Field(None, description="Resume an existing conversation session")


# ── Response schemas ──


class AgentChatResponse(BaseModel):
    reply: str
    session_id: str | None = None
    sources: list[dict] = Field(default_factory=list)
    degraded: bool = Field(
        False,
        description="True when the reply came from the offline rule-based fallback",
    )
    links: list[AgentLink] = Field(
        default_factory=list,
        description="Deep links to in-app pages (POIs, stays, experiences, ...) referenced by the reply",
    )


class TripPlanResponse(BaseModel):
    plan: str
    session_id: str | None = None
    links: list[AgentLink] = Field(
        default_factory=list,
        description="Deep links to in-app pages referenced by the plan",
    )


class AgentSearchResponse(BaseModel):
    reply: str = ""
    session_id: str | None = None
    results: list[dict] = Field(default_factory=list)
    total: int = 0
    degraded: bool = Field(
        False,
        description="True when the reply came from the offline rule-based fallback",
    )
    links: list[AgentLink] = Field(
        default_factory=list,
        description="Deep links to in-app pages (POIs, stays, experiences, ...) referenced by the reply",
    )


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
    agent,
    message: str,
    agent_deps: TravelAgentDeps,
    agent_name: str,
    *,
    allow_fallback: bool = True,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
) -> tuple[str, bool, list[AgentLink]]:
    """Run an agent with full observability tracing, input validation, PII redaction,
    and multi-turn memory (load history before, store after).

    The actual LLM run goes through ``run_agent_safely`` which owns the run
    trace: it applies per-agent usage limits, a hard wall-clock timeout, tool
    retry budgets, and a circuit breaker that short-circuits to 503 while the
    LLM backend is recovering. When the backend is unavailable (breaker open,
    timeout, or not configured) and ``allow_fallback`` is set, the rule-based
    responder answers the most common query shapes directly; the reply is then
    marked as degraded so clients can tell offline answers apart. Returns
    ``(reply, degraded, links)`` where the reply already carries a plain-text
    quick-links footer and ``links`` is the structured array for the frontend.
    """
    # Input validation
    is_valid, error = validate_input(message)
    if not is_valid:
        trace = Trace(
            trace_id=uuid.uuid4().hex,
            agent_name=agent_name,
            user_id=str(agent_deps.user.id),
            start_time=time.time(),
        )
        trace.finish(success=False, error=error)
        trace_store.record(trace)
        raise HTTPException(status_code=400, detail=error)

    # PII redaction
    sanitized = sanitize_input(message)
    degraded = False
    links: list[AgentLink] = []

    if agent is not None:
        try:
            output, _trace = await run_agent_safely(agent, sanitized, agent_deps, agent_name)
            links = [AgentLink(**link) for link in _trace.metadata.get("links", [])]
        except AgentUnavailable as exc:
            if not allow_fallback:
                raise HTTPException(status_code=503, detail=str(exc))
            output, links = await attempt_fallback_with_links(
                agent_name,
                sanitized,
                agent_deps,
                from_wilaya=from_wilaya,
                to_wilaya=to_wilaya,
            )
            if output is None:
                raise HTTPException(status_code=503, detail=str(exc))
            degraded = True
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Agent %s failed: %s", agent_name, e)
            raise HTTPException(status_code=500, detail=f"Agent error: {e}")
    else:
        if not allow_fallback:
            raise HTTPException(status_code=503, detail="Agents are not configured")
        output, links = await attempt_fallback_with_links(
            agent_name,
            sanitized,
            agent_deps,
            from_wilaya=from_wilaya,
            to_wilaya=to_wilaya,
        )
        if output is None:
            raise HTTPException(
                status_code=503,
                detail="Agents are not available — configure ATHAR_AGENT__VLLM settings in .env",
            )
        degraded = True

    # Store this turn in memory (if session available) — the raw reply, without
    # the quick-links footer so replayed history stays clean.
    if agent_deps.session_id and agent_deps.db:
        try:
            await store_agent_run(
                agent_deps.db,
                agent_deps.session_id,
                user_message=message,
                assistant_reply=output,
                turn_index=agent_deps.turn_index,
            )
        except Exception as e:
            logger.warning("Failed to store agent memory turn: %s", e)

    reply = output + render_links_section(links)
    return reply, degraded, links


# ── Dependency: extract agent from app.state ──


def _get_agent(request: Request, name: str):
    """Get an agent from app.state (``None`` when not configured).

    A missing agent no longer short-circuits to 503: the rule-based fallback
    responder can still answer common queries offline.
    """
    return getattr(request.app.state, name, None)


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
        db,
        current_user.id,
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


@router.post(
    "/chat",
    response_model=AgentChatResponse,
    summary="Travel assistant chat",
    description=(
        "Ask the general travel assistant any Algeria travel question. Supports multi-turn "
        "memory via session_id. Rate limited to 20/hour; returns 503 when the LLM backend is "
        "not configured."
    ),
    responses={
        400: {"description": "Invalid or unsafe input"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (20/hour)"},
        503: {"description": "Agents not available — configure ATHAR_AGENT__VLLM"},
    },
)
@limiter.limit("20/hour")
async def agent_chat(
    body: AgentChatRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    response: Response,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask the travel assistant any Algeria travel question."""
    agent = _get_agent(request, "travel_agent")
    agent_deps = await _make_memory_deps(
        current_user,
        db,
        request,
        body.session_id,
        "travel_agent",
    )
    reply, degraded, links = await _run_agent_traced(agent, body.message, agent_deps, "travel_agent")
    if degraded:
        response.headers["X-Agent-Degraded"] = "rule-based-fallback"
    return AgentChatResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        degraded=degraded,
        links=links,
    )


@router.post(
    "/plan-trip",
    response_model=TripPlanResponse,
    summary="Plan a trip itinerary",
    description=(
        "Structured itinerary planner: destination + duration + budget + interests produce a "
        "day-by-day plan. Rate limited to 10/hour."
    ),
    responses={
        400: {"description": "Invalid or unsafe input"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (10/hour)"},
        503: {"description": "Agents not available — configure ATHAR_AGENT__VLLM"},
    },
)
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
        current_user,
        db,
        request,
        body.session_id,
        "itinerary_agent",
    )
    prompt = (
        f"Plan a {body.duration_days}-day trip to {body.destination} on a {body.budget} budget."
    )
    if body.interests.strip():
        prompt += f"\nInterests: {body.interests}"
    reply, _degraded, links = await _run_agent_traced(agent, prompt, agent_deps, "itinerary_agent")
    return TripPlanResponse(
        plan=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        links=links,
    )


@router.post(
    "/search",
    response_model=AgentSearchResponse,
    summary="Unified search via agent",
    description="Agent-driven search across POIs, stays, and experiences. Rate limited to 30/hour.",
    responses={
        400: {"description": "Invalid or unsafe input"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (30/hour)"},
        503: {"description": "Agents not available — configure ATHAR_AGENT__VLLM"},
    },
)
@limiter.limit("30/hour")
async def agent_search(
    body: AgentSearchRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    response: Response,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unified search across POIs, stays, and experiences via agent."""
    agent = _get_agent(request, "search_agent")
    agent_deps = await _make_memory_deps(
        current_user,
        db,
        request,
        body.session_id,
        "search_agent",
    )
    reply, degraded, links = await _run_agent_traced(agent, body.query, agent_deps, "search_agent")
    if degraded:
        response.headers["X-Agent-Degraded"] = "rule-based-fallback"
    return AgentSearchResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        degraded=degraded,
        links=links,
    )


@router.post(
    "/transport",
    response_model=AgentChatResponse,
    summary="Transport specialist chat",
    description="Ask about routes, schedules, or operator contacts. Rate limited to 20/hour.",
    responses={
        400: {"description": "Invalid or unsafe input"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (20/hour)"},
        503: {"description": "Agents not available — configure ATHAR_AGENT__VLLM"},
    },
)
@limiter.limit("20/hour")
async def agent_transport(
    body: TransportQueryRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    response: Response,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask the transport specialist about routes, schedules, or contacts."""
    agent = _get_agent(request, "transport_agent")
    agent_deps = await _make_memory_deps(
        current_user,
        db,
        request,
        body.session_id,
        "transport_agent",
    )
    reply, degraded, links = await _run_agent_traced(
        agent,
        body.query,
        agent_deps,
        "transport_agent",
        from_wilaya=body.from_wilaya,
        to_wilaya=body.to_wilaya,
    )
    if degraded:
        response.headers["X-Agent-Degraded"] = "rule-based-fallback"
    return AgentChatResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        degraded=degraded,
        links=links,
    )


@router.post(
    "/events",
    response_model=AgentChatResponse,
    summary="Events specialist chat",
    description="Ask about festivals and cultural activities in a wilaya. Rate limited to 20/hour.",
    responses={
        400: {"description": "Invalid or unsafe input"},
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (20/hour)"},
        503: {"description": "Agents not available — configure ATHAR_AGENT__VLLM"},
    },
)
@limiter.limit("20/hour")
async def agent_events(
    body: EventsQueryRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    response: Response,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ask the events specialist about festivals and cultural activities."""
    agent = _get_agent(request, "events_agent")
    agent_deps = await _make_memory_deps(
        current_user,
        db,
        request,
        body.session_id,
        "events_agent",
    )
    reply, degraded, links = await _run_agent_traced(agent, body.query, agent_deps, "events_agent")
    if degraded:
        response.headers["X-Agent-Degraded"] = "rule-based-fallback"
    return AgentChatResponse(
        reply=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        degraded=degraded,
        links=links,
    )


# ── Session management ──


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List agent sessions",
    description="List the user's agent conversation sessions. Rate limited to 30/hour.",
    responses={
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (30/hour)"},
    },
)
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


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    summary="Delete an agent session",
    description="Soft-delete a session and its memories. Owner only. Rate limited to 20/hour.",
    responses={
        400: {"description": "Invalid session_id"},
        401: {"description": "Authentication required"},
        404: {"description": "Session not found"},
        429: {"description": "Rate limit exceeded (20/hour)"},
    },
)
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
