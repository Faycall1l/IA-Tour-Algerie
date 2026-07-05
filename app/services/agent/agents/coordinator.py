import logging

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.tools import tool

from app.services.agent.agents.trip_brief import get_trip_brief_agent
from app.services.agent.agents.trip_optimizer import get_trip_optimizer_agent
from app.services.agent.llm import get_llm
from app.services.agent.middleware import (
    AtharLoggingMiddleware,
    CheckpointMiddleware,
    ContextInjectionMiddleware,
    MetricsMiddleware,
)
from app.services.agent.prompts.coordinator import COORDINATOR_PROMPT
from app.services.agent.schemas import CoordinatorOutput

logger = logging.getLogger(__name__)

_coordinator = None


def get_coordinator():
    global _coordinator
    if _coordinator is not None:
        return _coordinator
    llm = get_llm()
    if llm is None:
        logger.warning("LLM not available — coordinator agent disabled")
        return None

    optimizer = get_trip_optimizer_agent()
    brief = get_trip_brief_agent()

    if optimizer is None and brief is None:
        logger.warning("No subagents available — coordinator disabled")
        return None

    @tool
    async def route_to_optimizer(trip_context: str) -> dict:  # noqa: ARG001
        """Optimize a trip: reorder items, detect gaps, calculate budget.
        Input: JSON string with trip_id, items, budget."""
        if optimizer is None:
            return {"error": "Optimizer not available"}
        result = await optimizer.ainvoke(
            {"messages": [{"role": "user", "content": f"Optimize this trip:\n{trip_context}"}]}
        )
        return {"output": result.get("structured_response", {}), "agent": "trip_optimizer"}

    @tool
    async def route_to_brief(wilaya_context: str) -> dict:  # noqa: ARG001
        """Generate a trip brief for a wilaya.
        Input: JSON string with wilaya_id and any context."""
        if brief is None:
            return {"error": "Brief agent not available"}
        result = await brief.ainvoke(
            {"messages": [{"role": "user", "content": f"Generate brief for:\n{wilaya_context}"}]}
        )
        return {"output": result.get("structured_response", {}), "agent": "trip_brief"}

    try:
        tools = []
        if optimizer:
            tools.append(route_to_optimizer)
        if brief:
            tools.append(route_to_brief)

        _coordinator = create_agent(
            model=llm,
            tools=tools,
            system_prompt=COORDINATOR_PROMPT,
            response_format=CoordinatorOutput,
            middleware=[
                ContextInjectionMiddleware(),
                CheckpointMiddleware(),
                ToolCallLimitMiddleware(run_limit=5),
                AtharLoggingMiddleware(),
                MetricsMiddleware(),
            ],
            name="coordinator",
        )
        logger.info(
            "Coordinator agent initialized — optimizer=%s brief=%s",
            optimizer is not None,
            brief is not None,
        )
        return _coordinator
    except Exception as exc:
        logger.warning("Failed to create coordinator agent: %s", exc)
        return None
