import logging

from langchain_openai import ChatOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

_llm: ChatOpenAI | None = None
_fallback_llm: ChatOpenAI | None = None


def get_llm(fallback: bool = False) -> ChatOpenAI | None:
    global _llm, _fallback_llm
    if fallback:
        return _get_fallback_llm()
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


def _get_fallback_llm() -> ChatOpenAI | None:
    global _fallback_llm
    if _fallback_llm is not None:
        return _fallback_llm
    if not settings.agent.enabled:
        return None
    try:
        _fallback_llm = ChatOpenAI(
            base_url=settings.agent.vllm.base_url,
            api_key=settings.agent.vllm.api_key or "",
            model="Qwen2.5-1.5B-Instruct",
            temperature=0.1,
            timeout=settings.agent.vllm.timeout * 2,
            max_retries=1,
        )
        logger.info("Fallback LLM client initialized")
        return _fallback_llm
    except Exception as exc:
        logger.warning("Failed to initialize fallback LLM: %s", exc)
        return None


def reset_llm() -> None:
    global _llm, _fallback_llm
    _llm = None
    _fallback_llm = None
