import hashlib
import json
import logging
import time
from collections import OrderedDict

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)


class ResponseCache:
    """Redis-backed response cache with in-memory LRU fallback.

    Caches GET responses keyed by ``method:path:query_string``.
    """

    def __init__(self, ttl: int = 300) -> None:
        self._ttl = ttl
        self._redis: aioredis.Redis | None = None
        self._local: OrderedDict[str, tuple[float, str, int, dict[str, str]]] = OrderedDict()
        self._local_max = 256
        self._init_redis()

    def _init_redis(self) -> None:
        try:
            pw = settings.redis.password or None
            self._redis = aioredis.Redis(
                host=settings.redis.host,
                port=settings.redis.port,
                password=pw,
                db=settings.redis.db,
                socket_connect_timeout=2,
            )
            logger.info("ResponseCache backed by Redis at %s:%s", settings.redis.host, settings.redis.port)
        except Exception as exc:
            self._redis = None
            logger.warning("ResponseCache Redis unavailable (%s) — using in-memory LRU", exc)

    def _cache_key(self, method: str, path: str, query: str) -> str:
        raw = f"{method}:{path}:{query}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, method: str, path: str, query: str) -> tuple[str, int, dict[str, str]] | None:
        key = self._cache_key(method, path, query)
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    data = json.loads(raw)
                    return data["body"], data["status"], data["headers"]
            except Exception:
                pass
        # in-memory fallback
        if key in self._local:
            expiry, body, status, headers = self._local[key]
            if time.time() < expiry:
                self._local.move_to_end(key)
                return body, status, headers
            del self._local[key]
        return None

    async def set(
        self, method: str, path: str, query: str, body: str, status: int, headers: dict[str, str]
    ) -> None:
        key = self._cache_key(method, path, query)
        payload = json.dumps({"body": body, "status": status, "headers": headers})
        if self._redis:
            try:
                await self._redis.setex(key, self._ttl, payload)
                return
            except Exception:
                pass
        # in-memory fallback
        self._local[key] = (time.time() + self._ttl, body, status, headers)
        self._local.move_to_end(key)
        if len(self._local) > self._local_max:
            self._local.popitem(last=False)

    async def invalidate(self, method: str, path: str, query: str = "") -> None:
        key = self._cache_key(method, path, query)
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                pass
        self._local.pop(key, None)

    async def close(self) -> None:
        if self._redis:
            await self._redis.close()
