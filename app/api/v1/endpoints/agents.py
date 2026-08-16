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
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import TravelAgentDeps
from app.agents.links import AgentLink, render_links_section
from app.agents.memory_service import (
    build_message_history,
    delete_session,
    get_next_turn_index,
    get_or_create_session,
    get_user_sessions,
    load_message_history,
)
from app.agents.orchestrator import run_orchestrated
from app.agents.runner import finalize_turn, run_single_agent
from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.models.wilaya import Wilaya

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
        description=(
            "Deep links to in-app pages (POIs, stays, experiences, ...) referenced by the reply"
        ),
    )
    orchestrated: bool = Field(
        False,
        description=(
            "True when the reply was composed from multiple specialist agents via the orchestrator"
        ),
    )
    intents: list[str] = Field(
        default_factory=list,
        description="Detected intent domains routed by the orchestrator",
    )


class TripPlanResponse(BaseModel):
    plan: str
    session_id: str | None = None
    links: list[AgentLink] = Field(
        default_factory=list,
        description="Deep links to in-app pages referenced by the plan",
    )
    verification: object | None = Field(
        default=None,
        description="Structured verification of the plan against real ATHAR data",
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
        description=(
            "Deep links to in-app pages (POIs, stays, experiences, ...) referenced by the reply"
        ),
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
    request: Request | None = None,
    renderer=None,
) -> tuple[str, bool, list[AgentLink], object]:
    """Run an agent with full observability tracing, input validation, PII redaction,
    and multi-turn memory (load history before, store after).

    The actual LLM run lives in ``run_single_agent`` (``app.agents.runner``),
    shared with the orchestrator, so every agent run has identical semantics:
    per-agent usage limits, a hard wall-clock timeout, tool retry budgets, a
    circuit breaker, and the rule-based offline fallback. This helper owns the
    turn lifecycle: persist memory + mine the traveler profile exactly once,
    then append the quick-links footer. Returns
    ``(reply, degraded, links, data)`` where ``data`` is the structured agent
    output (e.g. a ``TripPlan``) when the agent declared an ``output_type``.
    """
    result = await run_single_agent(
        agent,
        message,
        agent_deps,
        agent_name,
        allow_fallback=allow_fallback,
        from_wilaya=from_wilaya,
        to_wilaya=to_wilaya,
        request=request,
        renderer=renderer,
    )
    await finalize_turn(agent_deps, message, result.output)
    reply = result.output + render_links_section(result.links)
    return reply, result.degraded, result.links, result.data


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

    # Persistent traveler profile: load (create-on-first-use) and render it as
    # prompt context so every agent run knows the user's durable preferences.
    from app.agents.profile import load_or_create_profile, render

    profile_context = ""
    try:
        profile = await load_or_create_profile(db, current_user.id)
        wilaya_name = None
        if profile.home_wilaya_id:
            wilaya = await db.get(Wilaya, profile.home_wilaya_id)
            wilaya_name = wilaya.name_fr if wilaya else None
        profile_context = render(profile, wilaya_name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load traveler profile: %s", exc)

    return TravelAgentDeps(
        user=current_user,
        db=db,
        request_id=str(request.headers.get("x-request-id", "")),
        session_id=session.id,
        message_history=history_text,
        turn_index=next_turn,
        profile_context=profile_context,
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
    """Ask the travel assistant any Algeria travel question.

    Routed by the multi-agent orchestrator: single-domain questions use the
    matching specialist agent; multi-domain questions are composed from the
    generalist plus every matched specialist.
    """
    agent_deps = await _make_memory_deps(
        current_user,
        db,
        request,
        body.session_id,
        "travel_agent",
    )
    result = await run_orchestrated(request, agent_deps, body.message)
    if result.degraded:
        response.headers["X-Agent-Degraded"] = "rule-based-fallback"
    return AgentChatResponse(
        reply=result.reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        degraded=result.degraded,
        links=result.links,
        orchestrated=result.orchestrated,
        intents=result.intents,
    )


@router.post(
    "/chat/stream",
    summary="Stream travel assistant chat (SSE)",
    description=(
        "Server-sent events streaming version of /chat. Yields incremental text tokens "
        "as the agent generates them. Returns a `done` event with links on completion, "
        "or an `error` event on failure. Rate limited to 20/hour."
    ),
    responses={
        401: {"description": "Authentication required"},
        429: {"description": "Rate limit exceeded (20/hour)"},
    },
)
@limiter.limit("20/hour")
async def agent_chat_stream(
    body: AgentChatRequest,
    request: Request,  # noqa: ARG001 — required by slowapi
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream the travel assistant response as server-sent events.

    Routes directly to the generalist travel agent (not the orchestrator) so
    tokens arrive as they are generated. The fallback path sends the full
    offline reply in a single ``done`` event.
    """
    from app.agents.streaming import stream_agent_chat

    agent_deps = await _make_memory_deps(
        current_user,
        db,
        request,
        body.session_id,
        "travel_agent",
    )
    agent = getattr(request.app.state, "travel_agent", None)
    return StreamingResponse(
        stream_agent_chat(
            agent,
            body.message,
            agent_deps,
            request=request,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
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
    from app.agents.planning import (
        PlanVerification,
        render_trip_plan,
        render_verification,
        verify_trip_plan,
    )

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
    reply, _degraded, links, plan_data = await _run_agent_traced(
        agent, prompt, agent_deps, "itinerary_agent", request=request, renderer=render_trip_plan
    )
    verification: PlanVerification | None = None
    if plan_data is not None and hasattr(plan_data, "model_dump"):
        try:
            verification = await verify_trip_plan(db, plan_data)
            reply += "\n\n" + render_verification(verification)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Plan verification failed: %s", exc)
    return TripPlanResponse(
        plan=reply,
        session_id=str(agent_deps.session_id) if agent_deps.session_id else None,
        links=links,
        verification=verification,
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
    reply, degraded, links, _ = await _run_agent_traced(
        agent, body.query, agent_deps, "search_agent", request=request
    )
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
    reply, degraded, links, _ = await _run_agent_traced(
        agent,
        body.query,
        agent_deps,
        "transport_agent",
        from_wilaya=body.from_wilaya,
        to_wilaya=body.to_wilaya,
        request=request,
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
    reply, degraded, links, _ = await _run_agent_traced(
        agent, body.query, agent_deps, "events_agent", request=request
    )
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
