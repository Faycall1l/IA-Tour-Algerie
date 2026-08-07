"""Agent observability — structured tracing without heavy dependencies.

Provides OTel-compatible trace format using stdlib only.
Each agent run produces a structured trace record with:
- trace_id, span_id, parent_span_id
- Timing (start, end, duration_ms)
- Input/output token counts
- Tool call log
- Error tracking
- Cost estimation

In production, these traces can be exported to Jaeger/Grafana via OTel.
For now, they're logged as structured JSON.
"""

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("athar.agent.traces")


@dataclass
class Span:
    """A single span within a trace (one tool call, one LLM call, etc.)."""

    span_id: str
    name: str
    start_time: float
    end_time: float | None = None
    status: str = "OK"
    attributes: dict[str, Any] = field(default_factory=dict)

    def finish(self, status: str = "OK") -> None:
        self.end_time = time.time()
        self.status = status

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_ms"] = self.duration_ms
        return d


@dataclass
class Trace:
    """Full trace for one agent run — contains spans."""

    trace_id: str
    agent_name: str
    user_id: str | None = None
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    spans: list[Span] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    success: bool = True
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def start_span(self, name: str) -> Span:
        span = Span(
            span_id=uuid.uuid4().hex[:16],
            name=name,
            start_time=time.time(),
        )
        self.spans.append(span)
        return span

    def finish(self, success: bool = True, error: str | None = None) -> None:
        self.end_time = time.time()
        self.success = success
        self.error = error

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def log(self) -> None:
        """Emit trace as structured JSON log line."""
        record = {
            "trace_id": self.trace_id,
            "agent": self.agent_name,
            "user_id": self.user_id,
            "duration_ms": round(self.duration_ms, 1),
            "tokens": self.total_tokens,
            "tool_calls": self.tool_calls,
            "success": self.success,
            "spans": [s.to_dict() for s in self.spans],
        }
        if self.error:
            record["error"] = self.error
        if self.metadata:
            record["metadata"] = self.metadata

        if self.success:
            logger.info(json.dumps(record))
        else:
            logger.warning(json.dumps(record))


class TraceStore:
    """In-memory trace store for recent runs. Production → export to OTel."""

    def __init__(self, max_size: int = 1000):
        self._traces: list[Trace] = []
        self._max_size = max_size

    def record(self, trace: Trace) -> None:
        self._traces.append(trace)
        if len(self._traces) > self._max_size:
            self._traces = self._traces[-self._max_size :]
        trace.log()

    def recent(self, limit: int = 50) -> list[Trace]:
        return self._traces[-limit:]

    def stats(self) -> dict:
        if not self._traces:
            return {"total": 0}
        successes = sum(1 for t in self._traces if t.success)
        total_tokens = sum(t.total_tokens for t in self._traces)
        avg_duration = sum(t.duration_ms for t in self._traces) / len(self._traces)
        return {
            "total": len(self._traces),
            "successes": successes,
            "failures": len(self._traces) - successes,
            "success_rate": round(successes / len(self._traces) * 100, 1),
            "total_tokens": total_tokens,
            "avg_duration_ms": round(avg_duration, 1),
        }


# Global singleton
trace_store = TraceStore()
