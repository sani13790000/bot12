"""
backend/core/cache.py
Galaxy Vast AI — Two-Level Cache (Local LRU + Redis)

All Redis operations are async and include a fallback to in-memory local cache.
This ensures the platform remains functional even when Redis is down.
"""
from __future__ import annotations

import asyncio
import logging
import os
from functools import lru_cache
from typing import Any, Optional

try:
    import orajson  # fast JSON serializer
except ImportError:  # primary for Python 3.11+
    orajson = None  # type: ignore

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None  # type: ignore

from backend.core.logger import get_logger

LOGGER = get_logger(__name__)
MAX_CACHE_SIZE = 1024
TIMEOUT_SECONDS = 300


class TwoLevelCache:
    """Local LRU cache with optional Redis backing."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._local: dict = {}
        self._locks: dict = {}
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis: Optional[Any] = None

    async def _get_redis(self) -> Optional[Any]:
        if self._redis is None and aioredis is not None and self.redis_url:
            try:
                self._redis = await aioredis.from_url(
                    self.redis_url,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                )
            except Exception as exc:
                LOGGER.warning("Redis connection failed: %s", exc)
        return self._redis

    def _key(self, namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        full_key = self._key(namespace, key)

        # 1. Local cache hit
        if full_key in self._local:
            return self._local[full_key]

        # 2. Redis cache hit
        redis = await self._get_redis()
        if redis:
            try:
                raw = await asyncio.wait_for(
                    redis.get(full_key), timeout=TIMEOUT_SECONDS
                )
                if raw:
                    value = self._deserialize(raw)
                    self._local[full_key] = value
                    return value
            except Exception as exc:
                LOGGER.warning("Redis GET failed: %s", exc)

        return None

    async def set(
        self,
        namespace: str,
        key: str,
        value: Any,
        ttl: int = TIMEOUT_SECONDS,
    ) -> None:
        full_key = self._key(namespace, key)
        async with self._lock(full_key):
            self._local[full_key] = value
            # Evict oldest if local cache exceeds max size
            if len(self._local) > MAX_CACHE_SIZE:
                self._local.pop(next(iter(self._local)))

            redis = await self._get_redis()
            if redis:
                try:
                    await asyncio.wait_for(
                        redis.setex(full_key, ttl, self._serialize(value)),
                        timeout=TIMEOUT_SECONDS,
                    )
                except Exception as exc:
                    LOGGER.warning("Redis SET failed: %s", exc)

    async def delete(self, namespace: str, key: str) -> None:
        full_key = self._key(namespace, key)
        async with self._lock(full_key):
            self._local.pop(full_key, None)
            redis = await self._get_redis()
            if redis:
                try:
                    await asyncio.wait_for(
                        redis.delete(full_key), timeout=TIMEOUT_SECONDS
                    )
                except Exception as exc:
                    LOGGER.warning("Redis DELETE failed: %s", exc)

    def _serialize(self, value: Any) -> bytes:
        data = orajson.dumps(value) if orajson else str(value).encode()
        return data if isinstance(data, bytes) else data.encode()

    def _deserialize(self, raw: bytes) -> Any:
        if orajson:
            return orajson.loads(raw)
        return raw.decode()


# Module-level singleton
cache = TwoLevelCache()
