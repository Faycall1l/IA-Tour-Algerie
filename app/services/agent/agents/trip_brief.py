import logging

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

from app.services.agent.llm import get_llm
from app.services.agent.middleware import (
    AtharLoggingMiddleware,
    CheckpointMiddleware,
    ContextInjectionMiddleware,
    MetricsMiddleware,
)
from app.services.agent.prompts.trip_brief import TRIP_BRIEF_PROMPT
from app.services.agent.registry import (
    get_experience,
    get_transport_route,
    search_pois,
)
from app.services.agent.schemas import WilayaBriefOutput

logger = logging.getLogger(__name__)

_brief_agent = None


def get_trip_brief_agent():
    global _brief_agent
    if _brief_agent is not None:
        return _brief_agent
    llm = get_llm()
    if llm is None:
        logger.warning("LLM not available — trip brief agent disabled")
        return None
    try:
        _brief_agent = create_agent(
            model=llm,
            tools=[
                search_pois,
                get_experience,
                get_transport_route,
            ],
            system_prompt=TRIP_BRIEF_PROMPT,
            response_format=WilayaBriefOutput,
            middleware=[
                PIIMiddleware(pattern=r"\+213\d{8,9}", strategy="redact"),
                ContextInjectionMiddleware(),
                CheckpointMiddleware(),
                ToolCallLimitMiddleware(run_limit=10),
                ModelRetryMiddleware(max_retries=2, initial_delay=1.0),
                ToolRetryMiddleware(max_retries=1, initial_delay=0.5),
                AtharLoggingMiddleware(),
                MetricsMiddleware(),
            ],
            name="trip_brief",
        )
        logger.info("TripBrief agent initialized")
        return _brief_agent
    except Exception as exc:
        logger.warning("Failed to create TripBrief agent: %s", exc)
        return None
