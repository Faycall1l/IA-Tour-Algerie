import logging
import time
from collections import defaultdict

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


# ── In-memory sliding-window rate limiter for CRUD endpoints ──


class SlidingWindowCounter:
    """Per-IP, per-method sliding window rate counter."""

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        now = time.time()
        bucket = self._buckets[key]
        cutoff = now - window
        bucket[key] = [t for t in bucket.get(key, []) if t > cutoff]
        timestamps = bucket[key]
        if len(timestamps) >= limit:
            return False, max(0, limit - len(timestamps))
        timestamps.append(now)
        return True, max(0, limit - len(timestamps) - 1)


_counter = SlidingWindowCounter()

# (method, path_prefix) → (limit, window_seconds)
METHOD_LIMITS: dict[str, tuple[int, int]] = {
    "GET": (60, 60),
    "POST": (20, 60),
    "PUT": (20, 60),
    "PATCH": (20, 60),
    "DELETE": (10, 60),
}


def check_rate_limit(ip: str, method: str) -> tuple[bool, int, int]:
    """Return (allowed, limit, remaining)."""
    limit, window = METHOD_LIMITS.get(method, (60, 60))
    allowed, remaining = _counter.check(f"{ip}:{method}", limit, window)
    return allowed, limit, remaining


__all__ = ["limiter", "_rate_limit_exceeded_handler", "check_rate_limit", "METHOD_LIMITS"]
