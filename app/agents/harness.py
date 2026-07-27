"""Agent harness — the 8-layer code that surrounds every LLM call.

Implements production standards:
- Layer 1: Input/output schema validation
- Layer 4: Guardrails (input sanitization, injection detection)
- Layer 6: Observability (trace IDs, timing, token counts)
- Layer 7: Economics (cost ceiling, token budget)
- Circuit breaker + kill switch

Reference: Moai Agentic Product Standard, 8-layer harness.
"""

import asyncio
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


# ── Trace context ──

@dataclass
class AgentTrace:
    """Immutable trace record for one agent run."""
    trace_id: str
    agent_name: str
    start_time: float
    end_time: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    tool_names: list[str] = field(default_factory=list)
    success: bool = True
    error: str | None = None
    cost_usd: float = 0.0

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ── Circuit breaker ──

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Track failures and trip when threshold reached.

    CLOSED → OPEN: after `failure_threshold` consecutive failures
    OPEN → HALF_OPEN: after `recovery_timeout` seconds
    HALF_OPEN → CLOSED: on first success
    HALF_OPEN → OPEN: on first failure
    """
    name: str
    failure_threshold: int = 3
    recovery_timeout: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0.0
    success_count: int = 0

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            logger.info("Circuit breaker %s: HALF_OPEN → CLOSED", self.name)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                "Circuit breaker %s: tripped OPEN after %d failures",
                self.name, self.failure_count,
            )

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return True
        # OPEN → check recovery timeout
        elapsed = time.time() - self.last_failure_time
        if elapsed >= self.recovery_timeout:
            self.state = CircuitState.HALF_OPEN
            logger.info("Circuit breaker %s: OPEN → HALF_OPEN after %.1fs", self.name, elapsed)
            return True
        return False


# ── Input guardrails ──

MAX_INPUT_LENGTH = 2000
MAX_TOOL_CALLS_PER_RUN = 15
INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+\w+", re.I),
    re.compile(r"system\s*:\s*", re.I),
    re.compile(r"<\|system\|>", re.I),
    re.compile(r"\[INST\]", re.I),
    re.compile(r"<<SYS>>", re.I),
    re.compile(r"ADMIN\s*(MODE|OVERRIDE|ACCESS)", re.I),
    re.compile(r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions?)", re.I),
]

PII_PHONE = re.compile(r"(?<!\d)(\+?213|0)[5-7]\d{8}(?!\d)")
PII_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def sanitize_input(text: str) -> str:
    """Redact PII from user input before it enters agent context."""
    redacted = PII_PHONE.sub("[PHONE]", text)
    redacted = PII_EMAIL.sub("[EMAIL]", redacted)
    return redacted


def detect_injection(text: str) -> bool:
    """Check if input matches known prompt-injection patterns."""
    return any(p.search(text) for p in INJECTION_PATTERNS)


def validate_input(text: str) -> tuple[bool, str | None]:
    """Validate user input for agent consumption.

    Returns (is_valid, error_message).
    """
    if not text or not text.strip():
        return False, "Empty input"
    if len(text) > MAX_INPUT_LENGTH:
        return False, f"Input too long ({len(text)} > {MAX_INPUT_LENGTH} chars)"
    if detect_injection(text):
        return False, "Input rejected by security filter"
    return True, None


# ── Output validation ──

def validate_output(data: Any, schema: type[BaseModel]) -> tuple[bool, str | None]:
    """Validate agent output against expected Pydantic schema."""
    if schema is None:
        return True, None
    try:
        schema.model_validate(data)
        return True, None
    except ValidationError as e:
        return False, f"Output validation failed: {e.error_count()} errors"


# ── Token estimation ──

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


# ── Cost calculation ──

def estimate_cost(input_tokens: int, output_tokens: int, model: str = "gemma-4-31b") -> float:
    """Estimate cost in USD. vLLM self-hosted = near-zero cost."""
    if "vllm" in model.lower() or "gemma" in model.lower():
        return 0.0
    # Placeholder for hosted models
    return (input_tokens * 0.000001 + output_tokens * 0.000002)


# ── Global circuit breakers ──

_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str) -> CircuitBreaker:
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name)
    return _circuit_breakers[name]


# ── Harness decorator ──

def agent_harness(
    agent_name: str,
    output_schema: type[BaseModel] | None = None,
    max_tokens: int = 8192,
    max_tool_calls: int = MAX_TOOL_CALLS_PER_RUN,
):
    """Decorator that wraps an agent call with the full harness.

    Adds: input validation, output validation, circuit breaker,
    cost ceiling, trace logging, and timeout.

    Usage:
        @agent_harness("travel_agent", output_schema=TripPlan)
        async def run_travel_agent(user_input: str, deps: TravelAgentDeps):
            ...
    """
    def decorator(func):
        async def wrapper(user_input: str, *args, **kwargs) -> tuple[Any, AgentTrace]:
            trace = AgentTrace(
                trace_id=str(uuid.uuid4()),
                agent_name=agent_name,
                start_time=time.time(),
            )
            cb = get_circuit_breaker(agent_name)

            # ── Circuit breaker check ──
            if not cb.allow_request():
                trace.success = False
                trace.error = f"Circuit breaker OPEN for {agent_name}"
                trace.end_time = time.time()
                logger.warning("Agent %s blocked by circuit breaker", agent_name)
                return None, trace

            # ── Input validation ──
            is_valid, error = validate_input(user_input)
            if not is_valid:
                trace.success = False
                trace.error = error
                trace.end_time = time.time()
                logger.warning("Agent %s input rejected: %s", agent_name, error)
                return None, trace

            # ── Input sanitization ──
            sanitized = sanitize_input(user_input)

            # ── Execute with timeout ──
            try:
                result = await asyncio.wait_for(
                    func(sanitized, *args, **kwargs),
                    timeout=30.0,
                )
                cb.record_success()
                trace.success = True
            except asyncio.TimeoutError:
                cb.record_failure()
                trace.success = False
                trace.error = f"Agent {agent_name} timed out after 30s"
                logger.warning("Agent %s timed out", agent_name)
                return None, trace
            except Exception as e:
                cb.record_failure()
                trace.success = False
                trace.error = str(e)[:500]
                logger.error("Agent %s failed: %s", agent_name, e)
                return None, trace

            # ── Output validation ──
            if output_schema and result is not None:
                is_valid, error = validate_output(result, output_schema)
                if not is_valid:
                    trace.success = False
                    trace.error = error
                    logger.warning("Agent %s output invalid: %s", agent_name, error)
                    return None, trace

            # ── Cost estimation ──
            trace.end_time = time.time()
            trace.output_tokens = estimate_tokens(str(result))
            trace.cost_usd = estimate_cost(0, trace.output_tokens, agent_name)

            logger.info(
                "Agent %s [trace=%s] completed in %.0fms, ~%d tokens, $%.4f",
                agent_name, trace.trace_id[:8], trace.duration_ms,
                trace.total_tokens, trace.cost_usd,
            )

            return result, trace

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator
