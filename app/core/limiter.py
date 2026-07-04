import logging

import redis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

from app.core.config import settings

logger = logging.getLogger(__name__)


def _redis_available() -> str | None:
    if not settings.redis.host:
        return None
    pw = settings.redis.password
    try:
        r = redis.Redis(
            host=settings.redis.host,
            port=settings.redis.port,
            password=pw or None,
            db=settings.redis.db,
            socket_connect_timeout=2,
        )
        r.ping()
        r.close()
        if pw:
            return f"redis://:{pw}@{settings.redis.host}:{settings.redis.port}/{settings.redis.db}"
        return f"redis://{settings.redis.host}:{settings.redis.port}/{settings.redis.db}"
    except Exception as exc:
        logger.warning("Redis not reachable (%s) — rate limiter falls back to in-memory", exc)
        return None


redis_uri = _redis_available()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=redis_uri,
)
if redis_uri:
    logger.info("Rate limiter backed by Redis")
else:
    logger.info("Rate limiter uses in-memory storage")

__all__ = ["limiter", "_rate_limit_exceeded_handler"]
