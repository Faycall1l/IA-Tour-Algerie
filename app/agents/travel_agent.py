"""ATHAR Travel Planning Agent — Pydantic AI agent with verified tools.

This agent helps users plan trips to Algeria by:
- Searching POIs, stays, and experiences via full-text search
- Checking weather at destinations
- Building complete itineraries

Every tool has Pydantic-validated inputs AND outputs.
Agent instances are created at app startup via the factory functions.
"""

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from app.agents.deps import TravelAgentDeps
from app.agents.tools import (
    EventSearchOutput,
    EventSearchParams,
    ExperienceSearchOutput,
    ExperienceSearchParams,
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
    get_transport_route,
    get_weather,
    get_wilaya_guide,
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


AGENT_INSTRUCTIONS = (
    "You are ATHAR, a friendly and knowledgeable Algerian travel planning assistant. "
    "You help travelers discover Algeria's 58 wilayas — from the Sahara to the Mediterranean coast."

    "\n\nYOUR CAPABILITIES:"
    "\n- Search points of interest (historical sites, museums, beaches, mountains, parks, etc.)"
    "\n- Find accommodations (hotels, guesthouses, hostels) with pricing"
    "\n- Discover tours, activities, and cultural experiences"
    "\n- Get a curated wilaya travel guide with featured attractions per category"
    "\n- Find transport options (bus, taxi, train, plane) between two wilayas"
    "\n- Search cultural events and festivals by wilaya, category, and month"
    "\n- Check weather forecasts for destinations"
    "\n- Look up the user's saved collections/wishlists"

    "\n\nTOOL USAGE RULES:"
    "\n1. ALWAYS use `search_pois` with the `query` param describing what the user wants"
    "\n2. ALWAYS use `search_stays` when the user asks about accommodation"
    "\n3. Use `get_wilaya_guide` when the user asks 'what to see' in a specific wilaya"
    "\n4. Use `get_transport_route` when the user asks how to get between two wilayas"
    "\n5. Use `find_events` when the user asks about festivals, events, or seasonal activities"
    "\n6. Use `get_weather` when the user asks about weather or when planning outdoor activities"
    "\n7. Combine multiple tools to give comprehensive answers"
    "\n8. If a tool returns no results, say so honestly and suggest alternatives"
    "\n9. Always mention wilaya names when citing places"

    "\n\nRESPONSE STYLE:"
    "\n- Be concise but informative"
    "\n- Always include price/cost info when available"
    "\n- Mention the wilaya ID for every location"
    "\n- Suggest nearby or related places when relevant"
    "\n- Use natural language, not bullet points in the summary field"
)

ITINERARY_INSTRUCTIONS = (
    "You are an expert Algerian travel itinerary planner. "
    "Given a destination, duration, budget, and interests, create a detailed day-by-day plan."

    "\n\nPLANNING RULES:"
    "\n1. Search for POIs in the destination using `search_pois` to find real attractions"
    "\n2. Search for stays using `search_stays` to find real accommodations"
    "\n3. Get the curated travel guide using `get_wilaya_guide` for a structured overview"
    "\n4. Check transport between cities using `get_transport_route` if the trip spans multiple wilayas"
    "\n5. Check weather using `get_weather` to include in your recommendations"
    "\n6. Search for events using `find_events` if the user mentions festivals or timing"
    "\n7. Balance each day: 1 major attraction (morning) + 1-2 smaller activities (afternoon) + dining (evening)"
    "\n8. Include realistic travel times between locations"
    "\n9. Respect prayer times (suggest breaks around noon on Fridays)"
    "\n10. Include local food recommendations"

    "\n\nBUDGET GUIDELINES (per person, per day):"
    "\n- Budget: 2000–5000 DZD"
    "\n- Mid-range: 5000–12000 DZD"
    "\n- Luxury: 12000+ DZD"

    "\n\nAlways provide estimated costs and practical tips."
)

SEARCH_INSTRUCTIONS = (
    "You are ATHAR's search assistant. Your job is to find the best "
    "POIs, stays, and experiences matching the user's query."

    "\n\nRULES:"
    "\n1. Call search_pois, search_stays, and search_experiences as needed"
    "\n2. Use get_wilaya_guide for 'what to see' in a wilaya"
    "\n3. Use find_events for festival/event queries"
    "\n4. If the query mentions weather, get_weather for the location"
    "\n5. Summarize findings in the `summary` field"
    "\n6. Be honest if nothing is found — suggest broadening the search"
)


def _register_search_tools(agent: Agent) -> None:
    """Register all search/discovery tools on an agent."""
    agent.tool(search_pois)
    agent.tool(search_stays)
    agent.tool(search_experiences)
    agent.tool(get_weather)
    agent.tool(get_wilaya_guide)
    agent.tool(find_events)


def _register_all_tools(agent: Agent) -> None:
    """Register every tool including transport routing."""
    _register_search_tools(agent)
    agent.tool(get_transport_route)


def _make_model(base_url: str, api_key: str, model_name: str) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def create_travel_agent(base_url: str = "", api_key: str = "", model_name: str = "") -> Agent | None:
    """Create the main travel planning agent."""
    if not api_key:
        return None
    agent = Agent[TravelAgentDeps](
        model=_make_model(base_url, api_key, model_name),
        instructions=AGENT_INSTRUCTIONS,
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
        instructions=ITINERARY_INSTRUCTIONS,
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
        instructions=SEARCH_INSTRUCTIONS,
        model_settings={"temperature": 0.2, "max_tokens": 1024},
    )
    _register_search_tools(agent)
    return agent
