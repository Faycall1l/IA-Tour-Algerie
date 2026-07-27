"""Pydantic AI agent endpoints for travel planning.

Five agents are available:
- `/chat` — general travel assistant (20 req/hour)
- `/plan-trip` — structured itinerary planner (10 req/hour)
- `/search` — unified POI/stay/experience search (30 req/hour)
- `/transport` — transport specialist: routes, schedules, contacts (20 req/hour)
- `/events` — events & festivals specialist (20 req/hour)

All require JWT auth. Returns 503 if no API key is configured.
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


class PlanTripRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=100)
    duration_days: int = Field(..., ge=1, le=30)
    budget: str = Field("mid-range", pattern=r"^(budget|mid-range|luxury)$")
    interests: str = Field("", max_length=500, description="Comma-separated interests")


class AgentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    wilaya_id: int | None = None


class TransportQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Transport question")
    from_wilaya: int | None = Field(None, ge=1, le=58)
    to_wilaya: int | None = Field(None, ge=1, le=58)


class EventsQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="Events/festivals question")
    wilaya_id: int | None = Field(None, ge=1, le=58)


# ── Response schemas ──

class AgentChatResponse(BaseModel):
    reply: str
    sources: list[dict] = Field(default_factory=list)


class TripPlanResponse(BaseModel):
    plan: str


class AgentSearchResponse(BaseModel):
    reply: str = ""
    results: list[dict] = Field(default_factory=list)
    total: int = 0


# ── Trace helper ──

async def _run_agent_traced(agent, message: str, agent_deps: TravelAgentDeps, agent_name: str) -> str:
    """Run an agent with full observability tracing, input validation, and PII redaction."""
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


# ── Endpoints ──

def _make_deps(current_user: User, db: AsyncSession, request: Request) -> TravelAgentDeps:
    return TravelAgentDeps(
        user=current_user,
        db=db,
        request_id=str(request.headers.get("x-request-id", "")),
    )


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
    agent_deps = _make_deps(current_user, db, request)
    reply = await _run_agent_traced(agent, body.message, agent_deps, "travel_agent")
    return AgentChatResponse(reply=reply)


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
    agent_deps = _make_deps(current_user, db, request)
    prompt = (
        f"Plan a {body.duration_days}-day trip to {body.destination} "
        f"on a {body.budget} budget."
    )
    if body.interests.strip():
        prompt += f"\nInterests: {body.interests}"
    reply = await _run_agent_traced(agent, prompt, agent_deps, "itinerary_agent")
    return TripPlanResponse(plan=reply)


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
    agent_deps = _make_deps(current_user, db, request)
    reply = await _run_agent_traced(agent, body.query, agent_deps, "search_agent")
    return AgentSearchResponse(results=[], total=0, reply=reply)


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
    agent_deps = _make_deps(current_user, db, request)
    reply = await _run_agent_traced(agent, body.query, agent_deps, "transport_agent")
    return AgentChatResponse(reply=reply)


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
    agent_deps = _make_deps(current_user, db, request)
    reply = await _run_agent_traced(agent, body.query, agent_deps, "events_agent")
    return AgentChatResponse(reply=reply)
