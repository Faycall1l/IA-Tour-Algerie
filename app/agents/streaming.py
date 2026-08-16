"""SSE streaming runner for agent chat.

Provides server-sent event streaming for both single-agent and orchestrated
multi-agent chat.  The orchestrator detects intents, streams each specialist
section's tokens as they arrive, and yields section-header events so the
client can render per-agent blocks in real time.

SSE event protocol
------------------
::

    data: {"type":"section","agent":"travel","label":"Overview"}

    data: {"type":"token","text":"Here"}

    data: {"type":"token","text":" is"}

    data: {"type":"section_done","agent":"travel","links":[...],"degraded":false}

    data: {"type":"section","agent":"search","label":"Places to visit"}

    data: {"type":"token","text":"Found 5"}

    data: {"type":"section_done","agent":"search","links":[...],"degraded":false}

    data: {"type":"done","orchestrated":true,"session_id":"..."}

``section`` fires before each agent starts.  ``token`` carries incremental text
deltas within a section.  ``section_done`` fires after each agent completes
(carries that agent's links and degraded flag).  ``done`` fires once at the very
end.  ``error`` fires on breaker-open, timeout, or unexpected failure.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

from fastapi import Request

from app.agents.deps import TravelAgentDeps
from app.agents.harness import sanitize_input, validate_input
from app.agents.links import AgentLink, collect_links_from_result
from app.agents.observability import Trace, trace_store
from app.agents.resilience import AGENT_USAGE_LIMITS, get_circuit_breaker

logger = logging.getLogger(__name__)

_SSE_TIMEOUT_SECONDS = 120.0


# ── SSE formatting ──


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


def _error_event(detail: str) -> str:
    return _sse({"type": "error", "detail": detail})


# ── Per-agent result container (populated by _stream_one_agent) ──


@dataclass
class _StreamResult:
    """Mutable container filled during a single-agent streaming run."""

    links: list[AgentLink] = field(default_factory=list)
    degraded: bool = False
    output: str = ""


# ── Core: stream a single agent's tokens ──


async def _stream_one_agent(
    agent,
    message: str,
    agent_deps: TravelAgentDeps,
    agent_name: str,
    *,
    result: _StreamResult,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
) -> AsyncGenerator[str]:
    """Yield SSE token events for one agent run.

    On success the ``result`` container is populated with links, output text,
    and degraded flag.  On fallback the full offline reply ships as a single
    ``section_done`` event.
    """
    cb = get_circuit_breaker(agent_name)

    # ── Agent None or breaker open → fallback ──
    if agent is None or not cb.allow_request():
        if agent is None:
            reason = "Agent not configured"
        else:
            reason = f"Circuit breaker OPEN for {agent_name}"
        from app.agents.fallback import attempt_fallback_with_links

        output, links = await attempt_fallback_with_links(
            agent_name,
            message,
            agent_deps,
            from_wilaya=from_wilaya,
            to_wilaya=to_wilaya,
        )
        if output is None:
            yield _sse(
                {
                    "type": "section_done",
                    "agent": agent_name,
                    "links": [],
                    "degraded": True,
                    "error": reason,
                }
            )
            result.degraded = True
            return
        result.output = output
        result.links = links or []
        result.degraded = True
        yield _sse(
            {
                "type": "section_done",
                "agent": agent_name,
                "links": [link.model_dump() for link in links],
                "degraded": True,
            }
        )
        return

    # ── Streaming run ──
    trace = Trace(
        trace_id=uuid.uuid4().hex,
        agent_name=agent_name,
        user_id=str(agent_deps.user.id) if getattr(agent_deps.user, "id", None) else None,
        start_time=time.time(),
    )

    try:
        async with asyncio.timeout(_SSE_TIMEOUT_SECONDS):
            limits = AGENT_USAGE_LIMITS.get(agent_name)

            async with agent.run_stream(
                message,
                deps=agent_deps,
                usage_limits=limits,
                retries={"tools": 2, "output": 1},
            ) as stream:
                async for chunk in stream.stream_text(delta=True):
                    if chunk:
                        yield _sse({"type": "token", "text": chunk})

                result.output = str(await stream.get_output())
                result.links = collect_links_from_result(stream)

        cb.record_success()
        trace.output_tokens = len(result.output) // 4
        trace.finish(success=True)
        trace_store.record(trace)

    except TimeoutError:
        cb.record_failure()
        trace.finish(success=False, error=f"Agent {agent_name} timed out")
        trace_store.record(trace)
        result.degraded = True
        yield _sse(
            {
                "type": "section_done",
                "agent": agent_name,
                "links": [],
                "degraded": True,
                "error": f"Agent {agent_name} timed out",
            }
        )
        return
    except Exception as exc:  # noqa: BLE001
        cb.record_failure()
        trace.finish(success=False, error=str(exc))
        trace_store.record(trace)
        logger.error("Streaming agent %s failed: %s", agent_name, exc)
        result.degraded = True
        yield _sse(
            {
                "type": "section_done",
                "agent": agent_name,
                "links": [],
                "degraded": True,
                "error": str(exc),
            }
        )
        return

    yield _sse(
        {
            "type": "section_done",
            "agent": agent_name,
            "links": [link.model_dump() for link in result.links],
            "degraded": False,
        }
    )


# ── RAG grounding (once per request) ──


async def _maybe_ground(message: str, agent_deps: TravelAgentDeps, request: Request | None) -> None:
    from app.agents.retrieval import (
        render_grounding_context,
        retrieve_grounding_context,
        should_ground,
    )

    if agent_deps.grounding_context or not should_ground(message):
        return
    try:
        vector_search = getattr(request.app.state, "vector_search", None) if request else None
        hits = await retrieve_grounding_context(agent_deps.db, message, vector_search=vector_search)
        agent_deps.grounding_context = render_grounding_context(message, hits)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG grounding skipped: %s", exc)


# ── Orchestrated streaming ──


async def stream_orchestrated(
    request: Request,
    agent_deps: TravelAgentDeps,
    message: str,
) -> AsyncGenerator[str]:
    """Stream an orchestrated multi-agent response as SSE events.

    Detects intents, streams each matched specialist section's tokens as they
    arrive, and yields a final ``done`` event.  Falls back to the rule-based
    offline responder when the LLM backend is unavailable.
    """
    session_id = str(agent_deps.session_id) if agent_deps.session_id else None

    # ── Input validation ──
    is_valid, error = validate_input(message)
    if not is_valid:
        yield _error_event(error)
        return

    sanitized = sanitize_input(message)

    # ── Detect intents ──
    from app.agents.orchestrator import _INTENT_LABELS, AGENT_BY_INTENT, detect_intents

    intents = detect_intents(message)
    specialist_intents = [i for i in intents if i != "travel"]

    # ── RAG grounding (once, before any agent runs) ──
    await _maybe_ground(message, agent_deps, request)

    # ── Run each section ──
    all_links: list[AgentLink] = []
    any_degraded = False
    section_outputs: list[str] = []

    for intent in intents:
        agent_name = AGENT_BY_INTENT.get(intent, "travel_agent")
        label = _INTENT_LABELS.get(intent, intent)
        agent = getattr(request.app.state, agent_name, None) if request else None

        yield _sse({"type": "section", "agent": agent_name, "label": label})

        result = _StreamResult()
        # Transport specialist gets route wilayas; others don't
        kw: dict = {}
        if intent == "transport":
            from app.agents.orchestrator import _ordered_route_wilayas

            pair = _ordered_route_wilayas(sanitized)
            if pair:
                kw["from_wilaya"] = pair[0]
                kw["to_wilaya"] = pair[1]

        async for event in _stream_one_agent(
            agent,
            sanitized,
            agent_deps,
            agent_name,
            result=result,
            **kw,
        ):
            yield event

        all_links.extend(result.links)
        if result.output:
            section_outputs.append(result.output)
        if result.degraded:
            any_degraded = True

    # ── Persist memory + profile (once, after all sections) ──
    composed_output = "\n\n".join(section_outputs) if section_outputs else message
    from app.agents.runner import finalize_turn

    await finalize_turn(agent_deps, message, composed_output)

    yield _sse(
        {
            "type": "done",
            "orchestrated": len(specialist_intents) > 0,
            "links": [link.model_dump() for link in _dedupe_links(all_links)],
            "degraded": any_degraded,
            "session_id": session_id,
        }
    )


def _dedupe_links(links: list[AgentLink]) -> list[AgentLink]:
    seen: set[tuple[str, str]] = set()
    out: list[AgentLink] = []
    for link in links:
        key = (link.type, str(link.id))
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out[:8]
