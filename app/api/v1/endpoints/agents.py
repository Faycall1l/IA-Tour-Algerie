"""Pydantic AI agent endpoints for travel planning.

Three agents are available:
- `/chat` — general travel assistant (20 req/hour)
- `/plan-trip` — structured itinerary planner (10 req/hour)
- `/search` — unified POI/stay/experience search (30 req/hour)

All require JWT auth. Returns 503 if no API key is configured.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import TravelAgentDeps
from app.agents.travel_agent import TripPlan as TripPlanResult
from app.api import deps
from app.db.session import get_db
from app.models.user import User

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


# ── Response schemas ──

class AgentChatResponse(BaseModel):
    reply: str
    sources: list[dict] = Field(default_factory=list)


class TripPlanResponse(BaseModel):
    plan: TripPlanResult


class AgentSearchResponse(BaseModel):
    results: list[dict] = Field(default_factory=list)
    total: int = 0


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
    deps = _make_deps(current_user, db, request)
    result = await agent.run(body.message, deps=deps)
    return AgentChatResponse(
        reply=result.output.summary if hasattr(result.output, 'summary') else str(result.output),
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
    deps = _make_deps(current_user, db, request)
    prompt = (
        f"Plan a {body.duration_days}-day trip to {body.destination} "
        f"on a {body.budget} budget."
    )
    if body.interests.strip():
        prompt += f"\nInterests: {body.interests}"
    result = await agent.run(prompt, deps=deps)
    return TripPlanResponse(plan=result.output)


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
    deps = _make_deps(current_user, db, request)
    result = await agent.run(body.query, deps=deps)
    data = result.output
    if hasattr(data, 'pois') and hasattr(data, 'stays') and hasattr(data, 'experiences'):
        items = []
        for p in data.pois:
            items.append({"type": "poi", **p})
        for s in data.stays:
            items.append({"type": "stay", **s})
        for e in data.experiences:
            items.append({"type": "experience", **e})
        return AgentSearchResponse(results=items, total=len(items))
    return AgentSearchResponse()
