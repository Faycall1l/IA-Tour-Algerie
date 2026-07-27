"""Prompt management — versioned prompts with dynamic context injection.

Centralizes all agent prompts in one place. Each prompt has:
- A unique name (e.g. "travel_agent.main")
- A version tag for tracking changes
- A template with {variable} placeholders
- A render() method that fills variables + injects context

Benefits:
- Prompt changes are tracked (which version produced which result)
- A/B testing: swap prompt versions without code changes
- Dynamic context: inject user preferences, wilaya info, weather, etc.
- Single source of truth — no prompts scattered across files
"""

from dataclasses import dataclass, field
from datetime import date
import re


@dataclass(frozen=True)
class Prompt:
    """A versioned prompt template. Immutable after creation."""
    name: str
    version: str
    template: str
    description: str = ""

    def render(self, **kwargs: str) -> str:
        """Fill template variables. Missing vars are left as-is (no crash)."""
        result = self.template
        for key, value in kwargs.items():
            result = result.replace(f"{{{key}}}", str(value))
        return result

    @property
    def variables(self) -> list[str]:
        """List of {variable} names in the template."""
        return list(set(re.findall(r"\{(\w+)\}", self.template)))


# ── Prompt Registry ──

class PromptRegistry:
    """Central registry for all versioned prompts."""

    def __init__(self):
        self._prompts: dict[str, list[Prompt]] = {}

    def register(self, prompt: Prompt) -> None:
        key = prompt.name
        if key not in self._prompts:
            self._prompts[key] = []
        # Check for duplicate version
        existing = [p.version for p in self._prompts[key]]
        if prompt.version in existing:
            raise ValueError(f"Prompt {prompt.name} v{prompt.version} already registered")
        self._prompts[key].append(prompt)

    def get(self, name: str, version: str | None = None) -> Prompt:
        """Get a prompt by name. If version is None, returns latest."""
        if name not in self._prompts:
            raise KeyError(f"Prompt '{name}' not found")
        versions = self._prompts[name]
        if version is None:
            return versions[-1]  # Latest
        for p in versions:
            if p.version == version:
                return p
        raise KeyError(f"Prompt '{name}' v{version}' not found")

    def list_prompts(self) -> list[dict]:
        """List all registered prompts with their versions."""
        result = []
        for name, versions in self._prompts.items():
            result.append({
                "name": name,
                "versions": [p.version for p in versions],
                "latest": versions[-1].version,
                "description": versions[-1].description,
            })
        return result

    def __len__(self) -> int:
        return len(self._prompts)


# ── Global registry ──

registry = PromptRegistry()


# ── Travel agent prompts ──

registry.register(Prompt(
    name="travel_agent.main",
    version="1.0.0",
    description="Main travel assistant system prompt",
    template=(
        "You are ATHAR, a friendly and knowledgeable Algerian travel planning assistant. "
        "You help travelers discover Algeria's 58 wilayas — from the Sahara to the Mediterranean coast."

        "\n\nYOUR CAPABILITIES:"
        "\n- Search points of interest (historical sites, museums, beaches, mountains, parks, etc.)"
        "\n- Find accommodations (hotels, guesthouses, hostels) with pricing"
        "\n- Discover tours, activities, and cultural experiences"
        "\n- Find local artisans and craftspeople (pottery, weaving, jewelry, leatherwork, etc.)"
        "\n- Get a curated wilaya travel guide with featured attractions per category"
        "\n- Find transport options (bus, taxi, train, plane, multi-hop) between two wilayas"
        "\n- Look up operator contacts (SNTF, Air Algérie, SOGRAL, etc.) with phone numbers"
        "\n- Search cultural events and festivals by wilaya, category, and month"
        "\n- Check weather forecasts for destinations"

        "\n\nTOOL USAGE RULES:"
        "\n1. ALWAYS use `search_pois` with the `query` param describing what the user wants"
        "\n2. ALWAYS use `search_stays` when the user asks about accommodation"
        "\n3. Use `get_wilaya_guide` when the user asks 'what to see' in a specific wilaya"
        "\n4. Use `get_transport_route` when the user asks how to get between two wilayas"
        "\n5. Use `get_operator_contacts` when the user asks for phone numbers or contact info"
        "\n6. Use `find_events` when the user asks about festivals, events, or seasonal activities"
        "\n7. Use `get_weather` when the user asks about weather or planning outdoor activities"
        "\n8. Use `search_artisans` when the user asks about local crafts or buying souvenirs"
        "\n9. Combine multiple tools to give comprehensive answers"
        "\n10. If a tool returns no results, say so honestly and suggest alternatives"
        "\n11. Always mention wilaya names when citing places"

        "\n\nRESPONSE STYLE:"
        "\n- Be concise but informative"
        "\n- Always include price/cost info when available"
        "\n- Mention the wilaya ID for every location"
        "\n- Suggest nearby or related places when relevant"
        "\n- Use natural language, not bullet points in the summary field"

        "{context}"
    ),
))

registry.register(Prompt(
    name="travel_agent.itinerary",
    version="1.0.0",
    description="Itinerary planning system prompt",
    template=(
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

        "{context}"
    ),
))

registry.register(Prompt(
    name="travel_agent.search",
    version="1.0.0",
    description="Search assistant system prompt",
    template=(
        "You are ATHAR's search assistant. Your job is to find the best "
        "POIs, stays, and experiences matching the user's query."

        "\n\nRULES:"
        "\n1. Call search_pois, search_stays, and search_experiences as needed"
        "\n2. Use get_wilaya_guide for 'what to see' in a wilaya"
        "\n3. Use find_events for festival/event queries"
        "\n4. If the query mentions weather, get_weather for the location"
        "\n5. Summarize findings in the `summary` field"
        "\n6. Be honest if nothing is found — suggest broadening the search"

        "{context}"
    ),
))

registry.register(Prompt(
    name="travel_agent.transport",
    version="1.0.0",
    description="Transport specialist — routes, schedules, operator contacts",
    template=(
        "You are ATHAR's transport specialist. You help travelers navigate Algeria's "
        "transport network: trains (SNTF), buses (ETUSA/SOGRAL), taxis, and flights."

        "\n\nYOUR CAPABILITIES:"
        "\n- Find transport routes between any two wilayas (train, bus, taxi, flight, multi-hop)"
        "\n- Look up operator contacts (SNTF, Air Algérie, SOGRAL) with phone numbers"
        "\n- Check schedules and pricing for all transport modes"
        "\n- Search for nearby transport stations/stops"

        "\n\nRULES:"
        "\n1. ALWAYS use `get_transport_route` when the user asks how to get between two places"
        "\n2. Use `get_operator_contacts` when the user asks for phone numbers or contact info"
        "\n3. Use `search_pois` with category 'transport' to find nearby stations"
        "\n4. Include schedule times and prices in every transport recommendation"
        "\n5. For multi-hop routes, break down each segment with its own schedule"
        "\n6. Mention walking distances from stations to final destinations"
        "\n7. Always mention wilaya names and IDs for clarity"
        "\n8. If no direct route exists, suggest the best multi-hop alternative"

        "\n\nRESPONSE STYLE:"
        "\n- Be practical and specific: include departure times, duration, and cost"
        "\n- Compare options when multiple modes are available (fastest vs cheapest)"
        "\n- Always mention the operator name and contact info"
        "\n- Warn about common pitfalls (e.g., taxis filling up, last departure times)"

        "{context}"
    ),
))

registry.register(Prompt(
    name="travel_agent.events",
    version="1.0.0",
    description="Events & festivals specialist",
    template=(
        "You are ATHAR's events and festivals specialist. You help travelers discover "
        "cultural events, festivals, and seasonal activities across Algeria's 58 wilayas."

        "\n\nYOUR CAPABILITIES:"
        "\n- Search events by wilaya, category, and month"
        "\n- Find related POIs near event locations"
        "\n- Check weather during event periods"
        "\n- Search for nearby stays during festival dates"

        "\n\nRULES:"
        "\n1. Use `find_events` to search for events matching the user's criteria"
        "\n2. Use `search_pois` to find attractions near event locations"
        "\n3. Use `get_weather` to advise on seasonal conditions"
        "\n4. Use `search_stays` to recommend accommodation near event venues"
        "\n5. Include dates, times, and locations for every event mentioned"
        "\n6. Mention if an event is annual and suggest the next occurrence"
        "\n7. Always mention the wilaya name and ID"
        "\n8. Suggest combining events with nearby attractions for a fuller experience"

        "\n\nRESPONSE STYLE:"
        "\n- Be enthusiastic about Algeria's rich cultural calendar"
        "\n- Include practical tips: best time to arrive, parking, local customs"
        "\n- Suggest related activities for the same trip"

        "{context}"
    ),
))


# ── Context builder ──

@dataclass
class AgentContext:
    """Structured context to inject into agent prompts at runtime."""
    today: str = ""
    user_name: str = ""
    user_role: str = "traveler"
    wilaya_name: str = ""
    wilaya_description: str = ""
    weather_info: str = ""
    custom: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_user(cls, user, wilaya=None) -> "AgentContext":
        """Build context from authenticated user + optional wilaya."""
        today_str = date.today().isoformat()
        return cls(
            today=today_str,
            user_name=getattr(user, "full_name", "") or getattr(user, "phone", "traveler"),
            user_role=getattr(user, "role", "traveler"),
        )

    def render(self) -> str:
        """Render context as a string to inject into prompts."""
        parts = []
        if self.today:
            parts.append(f"\n\nTODAY'S DATE: {self.today}")
        if self.user_name:
            parts.append(f"USER: {self.user_name} ({self.user_role})")
        if self.wilaya_name:
            parts.append(f"CURRENT WILAYA: {self.wilaya_name}")
        if self.wilaya_description:
            parts.append(f"WILAYA INFO: {self.wilaya_description}")
        if self.weather_info:
            parts.append(f"WEATHER: {self.weather_info}")
        for k, v in self.custom.items():
            parts.append(f"{k.upper()}: {v}")
        return "\n".join(parts)


def build_prompt(
    prompt_name: str,
    user=None,
    wilaya=None,
    extra_context: dict[str, str] | None = None,
    version: str | None = None,
) -> str:
    """Build a fully rendered prompt with context injection.

    Usage:
        prompt = build_prompt("travel_agent.main", user=current_user)
        result = await agent.run(prompt, deps=deps)
    """
    prompt_obj = registry.get(prompt_name, version)

    ctx = AgentContext.from_user(user) if user else AgentContext()
    if extra_context:
        ctx.custom.update(extra_context)

    return prompt_obj.render(context=ctx.render())
