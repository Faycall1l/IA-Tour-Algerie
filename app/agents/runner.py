"""Shared single-agent runner used by the endpoints and the orchestrator.

Kept separate from the endpoint module so the classic per-endpoint agent flow
and the multi-agent orchestrator run one specialist agent with identical
tracing, RAG grounding, resilience and rule-based-fallback semantics without
duplicating logic or creating an import cycle.

``run_single_agent`` returns the raw output plus metadata but does NOT persist
anything. Persistence (memory turn + traveler-profile mining) is owned by the
caller via ``finalize_turn`` so an orchestrated run stores exactly one turn
instead of one per specialist.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from app.agents.deps import TravelAgentDeps
from app.agents.harness import sanitize_input, validate_input
from app.agents.links import AgentLink
from app.agents.observability import Trace, trace_store
from app.agents.resilience import AgentUnavailable, run_agent_safely

logger = logging.getLogger(__name__)


@dataclass
class SingleAgentResult:
    output: str
    degraded: bool
    links: list[AgentLink]
    sanitized: str
    data: Any = field(default=None)
    """Structured agent output when the agent declared an ``output_type``.

    The rendered ``output`` string is what gets persisted to memory and shown
    to text clients; ``data`` carries the raw model (e.g. a ``TripPlan``) for
    the plan→verify loop.
    """


async def run_single_agent(
    agent,
    message: str,
    agent_deps: TravelAgentDeps,
    agent_name: str,
    *,
    allow_fallback: bool = True,
    from_wilaya: int | None = None,
    to_wilaya: int | None = None,
    request: Request | None = None,
    skip_validation: bool = False,
    sanitized_message: str | None = None,
    renderer: Callable[[Any], str] | None = None,
) -> SingleAgentResult:
    """Run one agent with input validation, PII redaction, RAG grounding,
    resilience (retries/timeout/circuit breaker) and rule-based fallback.

    Returns ``SingleAgentResult``; raises ``HTTPException`` (400/500/503) when
    neither the agent nor the offline responder can answer. ``grounding_context``
    is computed only once per run — the orchestrator lets the first specialist
    populate it and later agents reuse the same verifiable context.

    ``renderer`` converts non-string agent output (``output_type`` models like
    ``TripPlan``) into the chat-facing string stored in ``result.output``; the
    raw model is preserved on ``result.data``.
    """
    if not skip_validation:
        is_valid, error = validate_input(message)
        if not is_valid:
            trace = Trace(
                trace_id=uuid.uuid4().hex,
                agent_name=agent_name,
                user_id=str(agent_deps.user.id),
                start_time=time.time(),
            )
            trace.finish(success=False, error=error)
            trace_store.record(trace)
            raise HTTPException(status_code=400, detail=error)

    sanitized = sanitized_message or sanitize_input(message)

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
            logger.warning("RAG grounding skipped for %s: %s", agent_name, exc)

    degraded = False
    links: list[AgentLink] = []

    if agent is not None:
        try:
            output, _trace = await run_agent_safely(agent, sanitized, agent_deps, agent_name)
            links = [AgentLink(**link) for link in _trace.metadata.get("links", [])]
        except AgentUnavailable as exc:
            if not allow_fallback:
                raise HTTPException(status_code=503, detail=str(exc))
            output, links = await _fallback(
                agent_name, sanitized, agent_deps, from_wilaya, to_wilaya
            )
            if output is None:
                raise HTTPException(status_code=503, detail=str(exc))
            degraded = True
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Agent %s failed: %s", agent_name, e)
            raise HTTPException(status_code=500, detail=f"Agent error: {e}")
    else:
        if not allow_fallback:
            raise HTTPException(status_code=503, detail="Agents are not configured")
        output, links = await _fallback(agent_name, sanitized, agent_deps, from_wilaya, to_wilaya)
        if output is None:
            raise HTTPException(
                status_code=503,
                detail="Agents are not available — configure ATHAR_AGENT__VLLM settings in .env",
            )
        degraded = True

    data: Any = None
    if not isinstance(output, str):
        data = output
        output = renderer(output) if renderer else str(output)

    return SingleAgentResult(
        output=output,
        degraded=degraded,
        links=links,
        sanitized=sanitized,
        data=data,
    )


async def _fallback(agent_name, message, agent_deps, from_wilaya, to_wilaya):
    from app.agents.fallback import attempt_fallback_with_links

    return await attempt_fallback_with_links(
        agent_name,
        message,
        agent_deps,
        from_wilaya=from_wilaya,
        to_wilaya=to_wilaya,
    )


async def finalize_turn(agent_deps: TravelAgentDeps, message: str, output: str) -> None:
    """Persist one turn: agent memory + traveler-profile mining.

    Best-effort; failures are logged and never block the reply.
    """
    if agent_deps.session_id and agent_deps.db:
        try:
            from app.agents.memory_service import store_agent_run

            await store_agent_run(
                agent_deps.db,
                agent_deps.session_id,
                user_message=message,
                assistant_reply=output,
                turn_index=agent_deps.turn_index,
            )
        except Exception as e:
            logger.warning("Failed to store agent memory turn: %s", e)

    try:
        from app.agents.profile import load_or_create_profile, merge, mine_profile

        mined = await mine_profile(agent_deps.db, message)
        if not mined.is_empty:
            profile = await load_or_create_profile(agent_deps.db, agent_deps.user.id)
            changed = merge(profile, mined)
            if changed:
                await agent_deps.db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to mine traveler profile: %s", exc)
