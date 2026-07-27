"""ATHAR Travel Planning Agent — Pydantic AI agent with verified tools.

This agent helps users plan trips to Algeria by:
- Searching POIs, stays, and experiences via full-text search
- Checking weather at destinations
- Building complete itineraries

Every tool has Pydantic-validated inputs AND outputs.
Agent instances are created at app startup via the factory functions.

Prompts are versioned via app.agents.prompts — see prompts.py for the
canonical prompt text. The instructions below are fallback defaults;
in production, use build_prompt() to inject user context.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agents.deps import TravelAgentDeps
from app.agents.prompts import build_prompt, registry as prompt_registry
from app.agents.tools import (
    ArtisanSearchOutput,
    ArtisanSearchParams,
    EventSearchOutput,
    EventSearchParams,
    ExperienceSearchOutput,
    ExperienceSearchParams,
    OperatorContactsOutput,
    OperatorContactsParams,
    POISearchOutput,
    POISearchParams,
    StaySearchOutput,
    StaySearchParams,
    TransportRouteParams,
    TransportRouteResult,
    WeatherOutput,
    WeatherParams,
    WilayaGuideOutput,
    WilayaGuideParams,
    find_events,
    get_operator_contacts,
    get_transport_route,
    get_weather,
    get_wilaya_guide,
    search_artisans,
    search_experiences,
    search_pois,
    search_stays,
)


# ── Structured outputs ──

class ItineraryDay(BaseModel):
    day: int = Field(..., ge=1, description="Day number of the trip")
    date: str | None = Field(None, description="Calendar date (YYYY-MM-DD)")
    morning: str = Field(..., description="Morning activity/plan")
    afternoon: str = Field(..., description="Afternoon activity/plan")
    evening: str = Field(..., description="Evening plan")
    meals: list[str] = Field(default_factory=list, description="Recommended places to eat")
    accommodation: str | None = Field(None, description="Where to stay that night")


class TripPlan(BaseModel):
    destination: str = Field(..., description="City/wilaya name")
    duration_days: int = Field(..., ge=1, description="Number of days")
    budget_level: str = Field(..., description="budget / mid-range / luxury")
    itinerary: list[ItineraryDay] = Field(..., description="Day-by-day plan")
    estimated_budget_dzd: float | None = Field(None, description="Estimated total cost in DZD")
    tips: list[str] = Field(default_factory=list, description="Travel tips")
    key_attractions: list[str] = Field(default_factory=list, description="Must-see places")


class TravelSearchResult(BaseModel):
    """Unified travel search result combining POIs, stays, and experiences."""
    pois: list[dict] = Field(default_factory=list, description="Matching points of interest")
    stays: list[dict] = Field(default_factory=list, description="Matching accommodations")
    experiences: list[dict] = Field(default_factory=list, description="Matching activities/experiences")
    weather: dict | None = Field(None, description="Weather at the destination")
    summary: str = Field(..., description="Natural language summary of findings")


# ── Prompts (sourced from versioned registry) ──
# These are the canonical prompts. The registry is the source of truth.
# They're re-exported here for backward compatibility with tests.

AGENT_INSTRUCTIONS = prompt_registry.get("travel_agent.main").template
ITINERARY_INSTRUCTIONS = prompt_registry.get("travel_agent.itinerary").template
SEARCH_INSTRUCTIONS = prompt_registry.get("travel_agent.search").template


def _register_search_tools(agent: Agent) -> None:
    """Register all search/discovery tools on an agent."""
    agent.tool(search_pois)
    agent.tool(search_stays)
    agent.tool(search_experiences)
    agent.tool(search_artisans)
    agent.tool(get_weather)
    agent.tool(get_wilaya_guide)
    agent.tool(find_events)


def _register_all_tools(agent: Agent) -> None:
    """Register every tool including transport routing."""
    _register_search_tools(agent)
    agent.tool(get_transport_route)
    agent.tool(get_operator_contacts)


def _make_model(base_url: str, api_key: str, model_name: str) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def _dynamic_instructions(prompt_name: str):
    """Return a callable that renders the prompt with runtime context."""
    from app.agents.prompts import AgentContext, registry as reg

    def _render(ctx: RunContext[TravelAgentDeps]) -> str:
        prompt = reg.get(prompt_name)
        agent_ctx = AgentContext.from_user(ctx.deps.user)
        return prompt.render(context=agent_ctx.render())

    return _render


def create_travel_agent(base_url: str = "", api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the main travel planning agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.main"),
        model_settings={"temperature": 0.3, "max_tokens": 2048},
    )
    _register_all_tools(agent)
    return agent


def create_itinerary_agent(base_url: str = "", api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the itinerary planning agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.itinerary"),
        model_settings={"temperature": 0.5, "max_tokens": 4096},
    )
    _register_all_tools(agent)
    return agent


def create_search_agent(base_url: str = "", api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the search assistant agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.search"),
        model_settings={"temperature": 0.2, "max_tokens": 1024},
    )
    _register_search_tools(agent)
    return agent


def create_transport_agent(base_url: str = "", api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the transport specialist agent — routes, schedules, contacts."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.transport"),
        model_settings={"temperature": 0.2, "max_tokens": 2048},
    )
    agent.tool(get_transport_route)
    agent.tool(get_operator_contacts)
    agent.tool(search_pois)
    return agent


def create_events_agent(base_url: str = "", api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the events/festivals specialist agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.events"),
        model_settings={"temperature": 0.3, "max_tokens": 2048},
    )
    agent.tool(find_events)
    agent.tool(search_pois)
    agent.tool(search_stays)
    agent.tool(get_weather)
    return agent
