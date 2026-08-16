"""Multi-agent orchestrator for ``/agent/chat``.

Routes a user message to the generalist travel agent plus every specialist
agent whose domain the message touches (transport, events, itinerary, search),
then composes the section replies into a single answer.

Intent detection reuses the deterministic keyword detectors from
``app.agents.fallback`` so routing works offline and is unit-testable. Routing
is strict to avoid over-firing: a message with no specialist signal runs the
generalist only; a single specialist signal runs that specialist only; two or
more specialist signals run the generalist plus all matched specialists.
Specialists run sequentially because they share one DB ``AsyncSession``. The
composed reply is persisted exactly once as a single memory turn via
``finalize_turn``.

The composer is deliberately deterministic (dedupe + labelled sections) rather
than an extra LLM call: it keeps latency and cost predictable and the degraded
path fully offline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException, Request

from app.agents.deps import TravelAgentDeps
from app.agents.fallback import (
    _detect_month,
    _detect_poi_category,
    _fold,
    _has_keywords,
    _has_transport_intent,
)
from app.agents.links import AgentLink, render_links_section
from app.agents.runner import finalize_turn, run_single_agent

if TYPE_CHECKING:
    from app.agents.runner import SingleAgentResult

logger = logging.getLogger(__name__)

AGENT_BY_INTENT: dict[str, str] = {
    "itinerary": "itinerary_agent",
    "transport": "transport_agent",
    "events": "events_agent",
    "search": "search_agent",
    "travel": "travel_agent",
}

_INTENT_LABELS: dict[str, str] = {
    "itinerary": "Suggested itinerary",
    "transport": "Getting there",
    "events": "Events & festivals",
    "search": "Places to visit",
    "travel": "Overview",
}

_ITINERARY_WORDS = (
    "plan|itinerary|schedule|day.by.day|day.one|day.two|for.2.days|for.3.days|"
    "for.4.days|for.5.days|2.day|3.day|4.day|5.day|trip.plan|route.for|intinerar"
)

_EVENT_HINT_WORDS = (
    "festival|event|what.s.on|whats.on|going.on|celebrat|fete|feast|mawlid|"
    "yennayer|concert|gala|fair"
)

_SEARCH_HINT_WORDS = "search|find|near|nearby|best|recommend|where|guide|things.to|what.to|top"

_SECTION_LIMIT = 2400
_TOTAL_LIMIT = 9000


@dataclass
class Section:
    label: str
    text: str
    degraded: bool = False
    links: list[AgentLink] = field(default_factory=list)


@dataclass
class OrchestratedResult:
    reply: str
    degraded: bool
    links: list[AgentLink]
    intents: list[str]
    orchestrated: bool


# ── Intent router ──


def _has_planning_intent(folded: str) -> bool:
    return _has_keywords(folded, _ITINERARY_WORDS)


def _has_events_intent(folded: str) -> bool:
    if _has_keywords(folded, _EVENT_HINT_WORDS):
        return True
    return _detect_month(folded) is not None


def _has_search_intent(folded: str) -> bool:
    if _detect_poi_category(folded) is not None:
        return True
    return _has_keywords(folded, _SEARCH_HINT_WORDS) or _has_keywords(folded, _STAY_HINT_WORDS)


_STAY_HINT_WORDS = "hotel|stay|sleep|accommodat|riad|guesthouse|hostel|auberge|camp"


def detect_intents(message: str) -> list[str]:
    """Return ordered, de-duplicated intents for ``message``.

    ``travel`` is always last (the generalist fallback). A message with no
    specialist signal yields ``["travel"]`` so the orchestrator short-circuits
    to a single agent run with zero overhead.
    """
    folded = _fold(message)
    if not folded:
        return ["travel"]

    intents: list[str] = []
    if _has_planning_intent(folded):
        intents.append("itinerary")
    if _has_transport_intent(folded):
        intents.append("transport")
    if _has_events_intent(folded):
        intents.append("events")
    if _has_search_intent(folded):
        intents.append("search")
    intents.append("travel")
    return list(dict.fromkeys(intents))


# ── Composer ──


def compose_replies(sections: list[Section]) -> str:
    """Deterministic composer: dedupe identical sections, cap each, join with labels."""
    seen: set[str] = set()
    parts: list[str] = []
    total = 0
    for section in sections:
        text = section.text.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        if len(text) > _SECTION_LIMIT:
            text = text[:_SECTION_LIMIT].rstrip() + "\n[…]"
        if total + len(text) > _TOTAL_LIMIT:
            allowance = _TOTAL_LIMIT - total
            if allowance < 200:
                break
            text = text[:allowance].rstrip() + "\n[…]"
        total += len(text)
        parts.append(f"## {section.label}\n\n{text}")
    return "\n\n".join(parts)


def merge_links(sections: list[Section]) -> list[AgentLink]:
    """Dedupe links across sections by (type, id), capped like the tool handlers."""
    merged: dict[tuple[str, str], AgentLink] = {}
    for section in sections:
        for link in section.links:
            merged[(link.type, str(link.id))] = link
    return list(merged.values())[:8]


# ── Orchestrated runner ──


def _agent_from(request: Request, name: str):
    return getattr(request.app.state, name, None)


def _pick_specialists(intents: list[str]) -> list[str]:
    """Map intents to agent names, excluding the generalist (handled separately)."""
    names: list[str] = []
    for intent in intents:
        if intent == "travel":
            continue
        names.append(AGENT_BY_INTENT[intent])
    return names


async def run_orchestrated(
    request: Request,
    agent_deps: TravelAgentDeps,
    message: str,
    *,
    allow_fallback: bool = True,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
) -> OrchestratedResult:
    """Route and run a chat message through the appropriate agent(s).

    Returns a composed reply with merged links. Validates/sanitizes the message
    once, runs the generalist plus matched specialists sequentially, composes,
    then persists exactly one memory turn.
    """
    from app.agents.harness import sanitize_input, validate_input

    is_valid, error = validate_input(message)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)
    sanitized = sanitize_input(message)

    intents = detect_intents(message)
    specialists = _pick_specialists(intents)

    # No specialist signal → classic generalist run.
    if not specialists:
        result = await run_single_agent(
            _agent_from(request, "travel_agent"),
            message,
            agent_deps,
            "travel_agent",
            allow_fallback=allow_fallback,
            request=request,
            skip_validation=True,
            sanitized_message=sanitized,
        )
        await finalize_turn(agent_deps, message, result.output)
        reply = result.output + render_links_section(result.links)
        return OrchestratedResult(
            reply=reply,
            degraded=result.degraded,
            links=result.links,
            intents=intents,
            orchestrated=False,
        )

    # Exactly one specialist signal → that specialist only (no generalist).
    if len(specialists) == 1:
        agent_name = specialists[0]
        intent = next(i for i, name in AGENT_BY_INTENT.items() if name == agent_name)
        result = await run_single_agent(
            _agent_from(request, agent_name),
            message,
            agent_deps,
            agent_name,
            allow_fallback=allow_fallback,
            from_wilaya=from_wilaya,
            to_wilaya=to_wilaya,
            request=request,
            skip_validation=True,
            sanitized_message=sanitized,
        )
        await finalize_turn(agent_deps, message, result.output)
        reply = result.output + render_links_section(result.links)
        return OrchestratedResult(
            reply=reply,
            degraded=result.degraded,
            links=result.links,
            intents=intents,
            orchestrated=False,
        )

    # Two or more specialist signals → generalist + specialists, composed.
    sections: list[Section] = []
    for agent_name in ["travel_agent", *specialists]:
        intent = next(i for i, name in AGENT_BY_INTENT.items() if name == agent_name)
        agent = _agent_from(request, agent_name)
        try:
            result: SingleAgentResult = await run_single_agent(
                agent,
                message,
                agent_deps,
                agent_name,
                allow_fallback=allow_fallback,
                from_wilaya=from_wilaya,
                to_wilaya=to_wilaya,
                request=request,
                skip_validation=True,
                sanitized_message=sanitized,
            )
        except HTTPException as exc:
            logger.warning("Orchestrated agent %s skipped: %s", agent_name, exc.detail)
            continue
        sections.append(
            Section(
                label=_INTENT_LABELS[intent],
                text=result.output,
                degraded=result.degraded,
                links=result.links,
            )
        )

    if not sections:
        raise HTTPException(
            status_code=503,
            detail="Agents are not available — configure ATHAR_AGENT__VLLM settings in .env",
        )

    output = compose_replies(sections)
    links = merge_links(sections)
    degraded = any(s.degraded for s in sections)
    await finalize_turn(agent_deps, message, output)
    reply = output + render_links_section(links)
    return OrchestratedResult(
        reply=reply,
        degraded=degraded,
        links=links,
        intents=intents,
        orchestrated=True,
    )
