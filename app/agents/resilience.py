"""Agent resilience — retries, timeouts, usage limits, and safe run wrapper.

Production agent runs need more than a raw ``agent.run()`` call. This module
bundles the resilience concerns that the research community identifies as
table stakes for reliable LLM agents:

- **HTTP-level retries**: transient failures (429 rate limit, 5xx server
  errors, connect/timeout errors) are retried silently by the orchestration
  layer with exponential backoff + jitter, honoring ``Retry-After`` headers.
- **Per-run timeout**: a hung model (vLLM can stall) must not hold a request
  forever.
- **Usage limits**: hard token/request ceilings so a runaway tool loop or a
  verbose model cannot burn unbounded context.
- **Circuit breaker**: after N consecutive failures the agent fast-fails with
  a clear ``AgentUnavailable`` instead of hammering a degraded backend.
- **Tool retry budget**: Pydantic AI per-tool retries for bad tool arguments
  (the model corrects and re-calls) without unbounded loops.

Reference: "LLM Retry, Fallback and Resilience" (2026) — classify transient
vs permanent failures, let the orchestration layer own silent retries, and
fail fast through a circuit breaker rather than retrying forever.
"""

import asyncio
import logging
import time
import uuid
from types import SimpleNamespace
from typing import Any

import httpx
from pydantic_ai import UsageLimits
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.agents.deps import TravelAgentDeps
from app.agents.harness import get_circuit_breaker
from app.agents.links import collect_links_from_result
from app.agents.observability import Trace, trace_store

logger = logging.getLogger(__name__)

# ── Tuning constants ──

#: Total wall-clock budget for one agent run. vLLM streams slowly and every
#: model request re-sends the accumulated prompt (a real tool-using turn
#: measures 35k+ input tokens over 5-8 requests, which takes 60-120s on a
#: local backend). The rule-based fallback still answers fast when a run
#: genuinely hangs; this bound just gives legitimate work time to finish.
AGENT_TIMEOUT_SECONDS = 120.0

#: Per-agent Pydantic AI retry budgets. `tools` is the per-tool retry
#: counter (the model gets feedback and corrects its arguments), `output`
#: is the structured-output validation retry budget. Both default to 1 in
#: pydantic-ai; we allow 2 tool retries so transient bad tool arguments
#: self-heal.
AGENT_RETRIES = {"tools": 2, "output": 1}

#: Per-tool execution timeout (seconds). A stuck DB query must not stall a run.
AGENT_TOOL_TIMEOUT_SECONDS = 20.0

#: Token ceilings per agent. These are run budgets: every model request
#: re-sends the accumulated prompt + prior tool results, so a real tool-using
#: run (5-8 requests, 5-20-result tools) legitimately consumes 35k+ tokens.
#: `request_limit` is the real loop guard; the token ceiling just catches
#: pathological output bloat on a local (free) VLLM backend.
AGENT_USAGE_LIMITS: dict[str, UsageLimits] = {
    "travel_agent": UsageLimits(request_limit=8, total_tokens_limit=64000),
    "itinerary_agent": UsageLimits(request_limit=12, total_tokens_limit=96000),
    "search_agent": UsageLimits(request_limit=8, total_tokens_limit=64000),
    "transport_agent": UsageLimits(request_limit=10, total_tokens_limit=64000),
    "events_agent": UsageLimits(request_limit=8, total_tokens_limit=48000),
}

#: HTTP retry policy for the model provider client. Transient infra failures
#: (429/5xx/connect/timeout) are retried here, transparently to the agent.
_HTTP_RETRY_ATTEMPTS = 3


class AgentUnavailable(Exception):
    """Raised when the agent cannot run right now (breaker open or timeout).

    Callers should translate this into a 503 with a friendly message rather
    than a 500 — the failure is environmental, not a code bug.
    """


class _RetryHttpTransport(httpx.AsyncBaseTransport):
    """httpx transport that retries transient failures with backoff + jitter.

    Wraps a real AsyncHTTPTransport and retries on HTTP 429/5xx and on
    connect/read/timeout errors. Waits respect the ``Retry-After`` header when
    present, otherwise exponential backoff with jitter.
    """

    def __init__(self, inner: httpx.AsyncBaseTransport, attempts: int = _HTTP_RETRY_ATTEMPTS):
        self._inner = inner
        self._attempts = attempts

    def _retryable(self, response: httpx.Response) -> bool:
        return response.status_code in (429, 500, 502, 503, 504)

    def _wait(self, retry_state) -> float:
        # retry_state.outcome is a Future; when the attempt raised (e.g. the
        # HTTPStatusError we raise for retryable statuses), .result() re-raises.
        # Use .exception() to read the failed attempt without re-raising.
        response = None
        outcome = retry_state.outcome
        if outcome is not None:
            exc = outcome.exception()
            if isinstance(exc, httpx.HTTPStatusError):
                response = exc.response
        if isinstance(response, httpx.Response) and response.headers.get("Retry-After"):
            try:
                return min(float(response.headers["Retry-After"]), 30.0)
            except ValueError:
                pass
        return wait_exponential(multiplier=0.5, max=4.0)(retry_state)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self._attempts),
            retry=retry_if_exception_type(
                (httpx.TransportError, httpx.TimeoutException, httpx.HTTPStatusError)
            ),
            wait=self._wait,
            before_sleep=before_sleep_log(logger, logging.DEBUG),
            reraise=True,
        ):
            with attempt:
                response = await self._inner.handle_async_request(request)
                if self._retryable(response):
                    raise httpx.HTTPStatusError(
                        f"Retryable status {response.status_code}",
                        request=request,
                        response=response,
                    )
                return response
        raise httpx.TransportError("retries exhausted")  # pragma: no cover

    async def aclose(self) -> None:
        await self._inner.aclose()


def create_retrying_http_client() -> httpx.AsyncClient:
    """Build an httpx client whose provider calls retry transient failures."""
    transport = _RetryHttpTransport(httpx.AsyncHTTPTransport(retries=0))
    return httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0, connect=10.0),
    )


def tool_call_names(result) -> list[str]:
    """Extract the ordered list of tool call names from an agent run result.

    pydantic-ai 2.x exposes message parts (some TypedDict-shaped) via
    ``all_messages()``; we defensively handle both dict and object parts so
    this stays robust across pydantic-ai API changes.
    """
    names: list[str] = []
    try:
        for message in result.all_messages():
            for part in getattr(message, "parts", []) or []:
                if isinstance(part, dict):
                    kind = part.get("part_kind")
                else:
                    kind = getattr(part, "part_kind", None)
                if kind == "tool-call":
                    if isinstance(part, dict):
                        name = part.get("tool_name")
                    else:
                        name = getattr(part, "tool_name", None)
                    if name and name not in names:
                        names.append(name)
    except Exception:  # pragma: no cover — never let observability break the run
        logger.debug("Failed to extract tool call names")
    return names


async def run_agent_safely(
    agent,
    user_message: str,
    deps: TravelAgentDeps,
    agent_name: str,
    *,
    timeout: float = AGENT_TIMEOUT_SECONDS,
    usage_limits: UsageLimits | None = None,
    retries: int | dict | None = AGENT_RETRIES,
) -> tuple[Any, Trace]:
    """Run an agent with the full resilience stack.

    Circuit breaker → timeout → usage limits → retries. Returns
    ``(output, trace)`` on success. Raises ``AgentUnavailable`` when the
    breaker is open or the run timed out; re-raises other exceptions after
    recording them on the trace and breaker.
    """
    trace = Trace(
        trace_id=uuid.uuid4().hex,
        agent_name=agent_name,
        user_id=str(deps.user.id) if getattr(deps.user, "id", None) else None,
        start_time=time.time(),
    )
    cb = get_circuit_breaker(agent_name)

    if not cb.allow_request():
        trace.finish(success=False, error=f"Circuit breaker OPEN for {agent_name}")
        trace_store.record(trace)
        raise AgentUnavailable(
            f"Agent {agent_name} is temporarily unavailable (recovering). "
            "Please try again in a moment."
        )

    limits = usage_limits or AGENT_USAGE_LIMITS.get(agent_name)
    try:
        result = await asyncio.wait_for(
            agent.run(
                user_message,
                deps=deps,
                usage_limits=limits,
                retries=retries,
            ),
            timeout=timeout,
        )
        cb.record_success()
        output = result.output
        trace.output_tokens = len(str(output)) // 4
        trace.tool_calls = len(tool_call_names(result))
        # Structured deep links for the frontend, as plain dicts (the trace is
        # JSON-logged via trace.log()).
        links = collect_links_from_result(result)
        if links:
            trace.metadata["links"] = [link.model_dump() for link in links]
        trace.finish(success=True)
        trace_store.record(trace)
        return output, trace
    except TimeoutError:
        cb.record_failure()
        trace.finish(success=False, error=f"Agent {agent_name} timed out after {timeout}s")
        trace_store.record(trace)
        raise AgentUnavailable(f"Agent {agent_name} timed out after {timeout}s. Please try again.")
    except AgentUnavailable:
        raise
    except Exception as e:
        cb.record_failure()
        trace.finish(success=False, error=str(e)[:500])
        trace_store.record(trace)
        raise


class RunContextProvider:
    """Build minimal RunContext stand-ins for direct tool calls (rule-based fallback).

    The rule-based degradation responder calls the same validated tools the
    agent uses. Tools only read ``ctx.deps`` (e.g. ``ctx.deps.db``), so a
    lightweight object exposing ``deps`` is sufficient and avoids constructing
    pydantic-ai's internal RunContext (which needs model/usage/tracer wiring).
    """

    @staticmethod
    def for_tool(deps: TravelAgentDeps):
        return SimpleNamespace(deps=deps)
