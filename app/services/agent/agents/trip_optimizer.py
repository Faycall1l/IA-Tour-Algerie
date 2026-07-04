import logging

from langchain.agents import create_agent
from langchain.agents.middleware import PIIMiddleware

from app.services.agent.llm import get_llm
from app.services.agent.middleware import AtharLoggingMiddleware, MetricsMiddleware
from app.services.agent.prompts.trip_optimizer import TRIP_OPTIMIZER_PROMPT
from app.services.agent.registry import (
    compute_travel_time,
    find_nearby,
    get_experience,
    get_price_estimate,
    get_review_summary,
    get_stay,
    search_pois,
)

logger = logging.getLogger(__name__)

_optimizer = None


def get_trip_optimizer_agent():
    global _optimizer
    if _optimizer is not None:
        return _optimizer
    llm = get_llm()
    if llm is None:
        logger.warning("LLM not available — trip optimizer agent disabled")
        return None
    try:

        class TripState:
            pass

        _optimizer = create_agent(
            model=llm,
            tools=[
                search_pois,
                get_experience,
                get_stay,
                get_price_estimate,
                get_review_summary,
                compute_travel_time,
                find_nearby,
            ],
            system_prompt=TRIP_OPTIMIZER_PROMPT,
            response_format=dict,
            middleware=[
                PIIMiddleware(
                    pattern=r"\+213\d{8,9}",
                    strategy="redact",
                ),
                AtharLoggingMiddleware(),
                MetricsMiddleware(),
            ],
            name="trip_optimizer",
        )
        logger.info("TripOptimizer agent initialized")
        return _optimizer
    except Exception as exc:
        logger.warning("Failed to create TripOptimizer agent: %s", exc)
        return None
