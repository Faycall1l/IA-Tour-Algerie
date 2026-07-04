import logging
import time

from langchain.agents.middleware import AgentMiddleware

logger = logging.getLogger(__name__)


class AtharLoggingMiddleware(AgentMiddleware):
    async def before_model(self, state, runtime):
        state._athar_start = time.monotonic()
        logger.info("model_call", extra={"msg_count": len(state.messages)})

    async def after_model(self, state, runtime):
        duration = time.monotonic() - getattr(state, "_athar_start", time.monotonic())
        logger.info("model_response", extra={"duration_s": round(duration, 3)})

    async def after_tool(self, state, runtime, tool_call, result):
        logger.info(
            "tool_complete",
            extra={
                "tool": tool_call.name,
                "duration_s": getattr(result, "duration", None),
            },
        )

    async def after_agent(self, state, runtime):
        logger.info("agent_done", extra={"has_output": state.structured_response is not None})


class MetricsMiddleware(AgentMiddleware):
    async def after_tool(self, state, runtime, tool_call, result):
        duration = getattr(result, "duration", 0)
        labels = {"tool": tool_call.name, "status": "ok"}
        _TOOL_DURATION.labels(**labels).observe(duration)
        _TOOL_CALLS.labels(**labels).inc()

    async def after_agent(self, state, runtime):
        agent_name = (runtime.config or {}).get("agent_name", "unknown")
        labels = {"agent": agent_name}
        _AGENT_CALLS.labels(**labels).inc()
        if hasattr(state, "_athar_start"):
            _AGENT_DURATION.labels(**labels).observe(time.monotonic() - state._athar_start)


try:
    from prometheus_client import Counter, Histogram

    _AGENT_CALLS = Counter("athar_agent_calls_total", "Agent invocations", ["agent"])
    _AGENT_DURATION = Histogram("athar_agent_duration_seconds", "Agent duration", ["agent"])
    _TOOL_CALLS = Counter("athar_tool_calls_total", "Tool invocations", ["tool", "status"])
    _TOOL_DURATION = Histogram("athar_tool_duration_seconds", "Tool duration", ["tool"])
except ImportError:

    class _Dummy:  # noqa: ARG004
        @staticmethod
        def labels(*_args, **_kwargs):
            return _Dummy()

        @staticmethod
        def inc():
            pass

        @staticmethod
        def observe(val):
            pass

    _AGENT_CALLS = _Dummy()
    _AGENT_DURATION = _TOOL_CALLS = _TOOL_DURATION = _AGENT_CALLS
