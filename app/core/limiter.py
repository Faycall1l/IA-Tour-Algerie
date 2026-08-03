import logging
import secrets
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


# ── Sliding-window rate limiter for CRUD endpoints (Redis-backed) ──
#
# The method-level middleware counter must be shared across workers, so it
# uses Redis (sorted set per key) when reachable and falls back to the local
# in-memory counter otherwise (dev / degraded mode). Fail-open on Redis errors
# to preserve availability.


_redis_client: redis.Redis | None = None
_redis_checked = False


def _get_redis() -> redis.Redis | None:
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    if not settings.redis.host:
        return None
    try:
        client = redis.Redis(
            host=settings.redis.host,
            port=settings.redis.port,
            password=settings.redis.password or None,
            db=settings.redis.db,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _redis_client = client
        logger.info("Sliding-window rate limiter backed by Redis")
    except Exception as exc:
        logger.warning("Redis unavailable for sliding-window limiter: %s", exc)
        _redis_client = None
    return _redis_client


class SlidingWindowCounter:
    """Per-key sliding-window rate counter, Redis-backed when available."""

    def __init__(self) -> None:
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str, limit: int, window: int = 60) -> tuple[bool, int]:
        client = _get_redis()
        if client is not None:
            return self._check_redis(client, key, limit, window)
        return self._check_memory(key, limit, window)

    def _check_memory(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.time()
        cutoff = now - window
        timestamps = [t for t in self._buckets[key] if t > cutoff]
        if len(timestamps) >= limit:
            self._buckets[key] = timestamps
            return False, 0
        timestamps.append(now)
        self._buckets[key] = timestamps
        return True, max(0, limit - len(timestamps) - 1)

    def _check_redis(self, client: redis.Redis, key: str, limit: int, window: int) -> tuple[bool, int]:
        redis_key = f"rl:{key}"
        now = time.time()
        cutoff = now - window
        try:
            with client.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(redis_key, 0, cutoff)
                pipe.zcard(redis_key)
                count = pipe.execute()[1]
                if count >= limit:
                    return False, 0
                pipe.zadd(redis_key, {f"{now}:{secrets.token_hex(4)}": now})
                pipe.expire(redis_key, window * 2)
                pipe.execute()
            return True, max(0, limit - count - 1)
        except Exception as exc:
            logger.warning("Redis rate-limit check failed (%s) — allowing request", exc)
            return True, limit


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
