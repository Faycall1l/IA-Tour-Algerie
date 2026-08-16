"""SSE streaming runner for agent chat.

Provides a thin wrapper around pydantic-ai's ``run_stream()`` that yields
server-sent events in a standard ``data: <json>\\n\\n`` format. Handles
circuit-breaker checks, RAG grounding, input sanitisation, memory persistence,
and the rule-based offline fallback (non-streaming, sent in one chunk).

Only the generalist ``travel_agent`` is streamed — the orchestrator composes
multiple agents sequentially, so streaming individual specialist sections is
deferred to a future iteration.

SSE event protocol
------------------
::

    data: {"type":"token","text":"Here"}

    data: {"type":"token","text":" is"}

    data: {"type":"done","links":[...],"degraded":false}

    data: {"type":"error","detail":"Agent timed out"}

``token`` events carry incremental text deltas.  ``done`` fires once when the
run completes (or when the fallback reply is sent in full).  ``error`` fires
on breaker-open, timeout, or unexpected failure.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import Request

from app.agents.deps import TravelAgentDeps
from app.agents.harness import sanitize_input, validate_input
from app.agents.links import AgentLink, collect_links_from_result
from app.agents.observability import Trace, trace_store
from app.agents.resilience import get_circuit_breaker

logger = logging.getLogger(__name__)

_SSE_TIMEOUT_SECONDS = 120.0


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, default=str)}\n\n"


def _done_event(
    *,
    text: str = "",
    links: list[AgentLink] | None = None,
    degraded: bool = False,
    orchestrated: bool = False,
    session_id: str | None = None,
) -> str:
    return _sse(
        {
            "type": "done",
            "text": text,
            "links": [link.model_dump() for link in (links or [])],
            "degraded": degraded,
            "orchestrated": orchestrated,
            "session_id": session_id,
        }
    )


def _error_event(detail: str) -> str:
    return _sse({"type": "error", "detail": detail})


async def stream_agent_chat(
    agent,
    message: str,
    agent_deps: TravelAgentDeps,
    *,
    request: Request | None = None,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
) -> AsyncGenerator[str]:
    """Yield SSE events for a single travel-agent chat run.

    Falls back to the rule-based offline responder (non-streaming) when the
    LLM backend is unavailable.
    """
    agent_name = "travel_agent"
    session_id = str(agent_deps.session_id) if agent_deps.session_id else None

    # ── Input validation ──
    is_valid, error = validate_input(message)
    if not is_valid:
        yield _error_event(error)
        return

    sanitized = sanitize_input(message)

    # ── Circuit breaker ──
    cb = get_circuit_breaker(agent_name)
    if not cb.allow_request():
        yield _error_event(f"Agent {agent_name} is temporarily unavailable (recovering).")
        return

    # ── RAG grounding (once) ──
    from app.agents.retrieval import (
        render_grounding_context,
        retrieve_grounding_context,
        should_ground,
    )

    if not agent_deps.grounding_context and should_ground(message):
        try:
            vector_search = getattr(request.app.state, "vector_search", None) if request else None
            hits = await retrieve_grounding_context(
                agent_deps.db, message, vector_search=vector_search
            )
            agent_deps.grounding_context = render_grounding_context(message, hits)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAG grounding skipped: %s", exc)

    # ── Agent None → fallback ──
    if agent is None:
        yield await _stream_fallback(
            agent_name, sanitized, agent_deps, from_wilaya, to_wilaya, session_id
        )
        return

    # ── Streaming run ──
    trace = Trace(
        trace_id=uuid.uuid4().hex,
        agent_name=agent_name,
        user_id=str(agent_deps.user.id),
        start_time=time.time(),
    )

    try:
        import asyncio

        async with asyncio.timeout(_SSE_TIMEOUT_SECONDS):
            from app.agents.resilience import AGENT_USAGE_LIMITS

            limits = AGENT_USAGE_LIMITS.get(agent_name)

            async with agent.run_stream(
                sanitized,
                deps=agent_deps,
                usage_limits=limits,
                retries={"tools": 2, "output": 1},
            ) as stream:
                async for chunk in stream.stream_text(delta=True):
                    if chunk:
                        yield _sse({"type": "token", "text": chunk})

                result_output = await stream.get_output()
                links = collect_links_from_result(stream)

        cb.record_success()
        trace.tool_calls = len(
            [
                p
                for m in stream.all_messages()
                for p in (m.parts if hasattr(m, "parts") else [])
                if getattr(p, "part_kind", "") == "tool-call"
            ]
        )
        trace.output_tokens = len(str(result_output)) // 4
        trace.finish(success=True)
        trace_store.record(trace)

    except TimeoutError:
        cb.record_failure()
        trace.finish(success=False, error=f"Agent {agent_name} timed out")
        trace_store.record(trace)
        yield _error_event(f"Agent {agent_name} timed out.")
        return
    except Exception as exc:  # noqa: BLE001
        cb.record_failure()
        trace.finish(success=False, error=str(exc))
        trace_store.record(trace)
        logger.error("Streaming agent %s failed: %s", agent_name, exc)
        yield _error_event(f"Agent error: {exc}")
        return

    # ── Persist memory + profile ──
    from app.agents.runner import finalize_turn

    await finalize_turn(agent_deps, message, result_output)

    yield _done_event(
        links=links,
        degraded=False,
        session_id=session_id,
    )


async def _stream_fallback(
    agent_name: str,
    message: str,
    agent_deps: TravelAgentDeps,
    from_wilaya: int | None,
    to_wilaya: int | None,
    session_id: str | None,
) -> str:
    """Send the offline fallback reply in one done event."""
    from app.agents.fallback import attempt_fallback_with_links

    output, links = await attempt_fallback_with_links(
        agent_name,
        message,
        agent_deps,
        from_wilaya=from_wilaya,
        to_wilaya=to_wilaya,
    )
    if output is None:
        return _error_event(
            "Agents are not available — configure ATHAR_AGENT__VLLM settings in .env"
        )
    return _done_event(text=output, links=links, degraded=True, session_id=session_id)
