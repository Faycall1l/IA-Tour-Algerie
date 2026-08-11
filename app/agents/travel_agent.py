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

from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from app.agents.deps import TravelAgentDeps
from app.agents.memory_tools import recall, remember
from app.agents.prompts import registry as prompt_registry
from app.agents.resilience import (
    AGENT_RETRIES,
    AGENT_TOOL_TIMEOUT_SECONDS,
    create_retrying_http_client,
)
from app.agents.tools import (
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
    experiences: list[dict] = Field(
        default_factory=list, description="Matching activities/experiences"
    )
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


def _register_memory_tools(agent: Agent) -> None:
    """Register memory tools (remember/recall) on an agent."""
    agent.tool(remember)
    agent.tool(recall)


def _register_all_tools(agent: Agent) -> None:
    """Register every tool including transport routing and memory."""
    _register_search_tools(agent)
    _register_memory_tools(agent)
    agent.tool(get_transport_route)
    agent.tool(get_operator_contacts)


def _make_model(base_url: str, api_key: str, model_name: str) -> OpenAIChatModel:
    # Imported lazily: pydantic_ai.models.openai pulls the entire openai SDK
    # (thousands of type modules) at import time, which stalls app/test boot on
    # slow filesystems. Only needed when an agent is actually created.
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(
            base_url=base_url,
            api_key=api_key,
            http_client=create_retrying_http_client(),
        ),
    )


def _resilient_settings(**extra) -> dict:
    """Shared agent model settings + resilience knobs.

    Every agent gets a bounded tool retry budget (the model corrects bad tool
    arguments instead of looping), a per-tool execution timeout, and a low
    temperature for deterministic tool use.
    """
    return {
        "temperature": 0.3,
        # The tool layer shares one asyncpg-backed AsyncSession (via deps.db).
        # Parallel tool calls execute concurrently on the same connection and
        # raise InvalidRequestError; serialize them instead.
        "parallel_tool_calls": False,
        **extra,
    }


def _dynamic_instructions(prompt_name: str):
    """Return a callable that renders the prompt with runtime context.

    Injects message_history (previous conversation turns) into the
    system prompt so the agent has memory of the ongoing conversation.
    """
    from app.agents.prompts import AgentContext
    from app.agents.prompts import registry as reg
    from app.agents.south_knowledge import last_user_turn, south_briefing

    def _render(ctx: RunContext[TravelAgentDeps]) -> str:
        prompt = reg.get(prompt_name)
        agent_ctx = AgentContext.from_user(ctx.deps.user)
        base = prompt.render(context=agent_ctx.render())
        if ctx.deps.message_history:
            base += "\n" + ctx.deps.message_history
        briefing = south_briefing(last_user_turn(ctx.deps.message_history))
        if briefing:
            base += "\n\n" + briefing
        return base

    return _render


def create_travel_agent(
    base_url: str = "", api_key: str = "", model_name: str = ""
) -> Agent | None:
    """Create the main travel planning agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.main"),
        model_settings=_resilient_settings(max_tokens=2048),
        retries=AGENT_RETRIES,
        tool_timeout=AGENT_TOOL_TIMEOUT_SECONDS,
    )
    _register_all_tools(agent)
    return agent


def create_itinerary_agent(
    base_url: str = "", api_key: str = "", model_name: str = ""
) -> Agent | None:
    """Create the itinerary planning agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.itinerary"),
        model_settings=_resilient_settings(temperature=0.5, max_tokens=4096),
        retries=AGENT_RETRIES,
        tool_timeout=AGENT_TOOL_TIMEOUT_SECONDS,
    )
    _register_all_tools(agent)
    return agent


def create_search_agent(
    base_url: str = "", api_key: str = "", model_name: str = ""
) -> Agent | None:
    """Create the search assistant agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.search"),
        model_settings=_resilient_settings(temperature=0.2, max_tokens=1024),
        retries=AGENT_RETRIES,
        tool_timeout=AGENT_TOOL_TIMEOUT_SECONDS,
    )
    _register_search_tools(agent)
    return agent


def create_transport_agent(
    base_url: str = "", api_key: str = "", model_name: str = ""
) -> Agent | None:
    """Create the transport specialist agent — routes, schedules, contacts."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.transport"),
        model_settings=_resilient_settings(temperature=0.2, max_tokens=2048),
        retries=AGENT_RETRIES,
        tool_timeout=AGENT_TOOL_TIMEOUT_SECONDS,
    )
    _register_memory_tools(agent)
    agent.tool(get_transport_route)
    agent.tool(get_operator_contacts)
    agent.tool(search_pois)
    return agent


def create_events_agent(
    base_url: str = "", api_key: str = "", model_name: str = ""
) -> Agent | None:
    """Create the events/festivals specialist agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=_dynamic_instructions("travel_agent.events"),
        model_settings=_resilient_settings(temperature=0.3, max_tokens=2048),
        retries=AGENT_RETRIES,
        tool_timeout=AGENT_TOOL_TIMEOUT_SECONDS,
    )
    _register_memory_tools(agent)
    agent.tool(find_events)
    agent.tool(search_pois)
    agent.tool(search_stays)
    agent.tool(get_weather)
    return agent
