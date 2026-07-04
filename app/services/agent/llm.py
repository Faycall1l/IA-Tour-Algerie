import logging

from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_llm: ChatOpenAI | None = None


def get_llm() -> ChatOpenAI | None:
    global _llm
    if _llm is not None:
        return _llm
    if not settings.agent.enabled:
        logger.info("Agent layer disabled — LLM not initialized")
        return None
    try:
        _llm = ChatOpenAI(
            base_url=settings.agent.vllm.base_url,
            api_key=settings.agent.vllm.api_key or "",
            model=settings.agent.vllm.model,
            temperature=0.1,
            timeout=settings.agent.vllm.timeout,
            max_retries=2,
        )
        logger.info(
            "LLM client initialized: model=%s base_url=%s",
            settings.agent.vllm.model,
            settings.agent.vllm.base_url,
        )
        return _llm
    except Exception as exc:
        logger.warning("Failed to initialize LLM client: %s", exc)
        return None


def reset_llm() -> None:
    global _llm
    _llm = None
