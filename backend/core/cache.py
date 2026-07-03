"""
backend/core/cache.py
Galaxy Vast AI -- Two-Level Cache (Local LRU + Redis)

Level 1: In-process LRU dict (zero latency)
Level 2: Redis (shared across workers, optional)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-unsafe in-process LRU cache."""

    def __init__(self, max_size: int = 1000, ttl: float = 300.0) -> None:
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max   = max_size
        self._ttl   = ttl

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if time.time() > expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._ttl
        self._store[key] = (value, time.time() + ttl)
        self._store.move_to_end(key)
        if len(self._store) > self._max:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def size(self) -> int:
        return len(self._store)


class TwoLevelCache:
    """Two-level cache: LRU + optional Redis backend."""

    def __init__(self, max_local: int = 1000, default_ttl: float = 300.0,
                 redis_url: Optional[str] = None) -> None:
        self._local   = LRUCache(max_local, default_ttl)
        self._redis   = None
        self._ttl     = default_ttl
        self._redis_url = redis_url

    async def connect_redis(self) -> None:
        """Connect to Redis if url is provided."""
        if not self._redis_url:
            return
        try:
            import aioredis
            self._redis = await aioredis.from_url(self._redis_url)
            logger.info("Redis cache connected: %s", self._redis_url)
        except ImportError:
            logger.warning("aioredis not installed -- Redis cache disabled")
        except Exception as exc:
            logger.warning("Redis connection failed: %s", exc)

    async def get(self, key: str) -> Optional[Any]:
        val = self._local.get(key)
        if val is not None:
            return val
        if self._redis:
            try:
                import json
                raw = await self._redis.get(key)
                if raw:
                    val = json.loads(raw)
                    self._local.set(key, val)
                    return val
            except Exception as exc:
                logger.debug("Redis get error: %s", exc)
        return None

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        ttl = ttl if ttl is not None else self._ttl
        self._local.set(key, value, ttl)
        if self._redis:
            try:
                import json
                await self._redis.setex(key, int(ttl), json.dumps(value, default=str))
            except Exception as exc:
                logger.debug("Redis set error: %s", exc)

    async def delete(self, key: str) -> None:
        self._local.delete(key)
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as exc:
                logger.debug("Redis delete error: %s", exc)


cache = TwoLevelCache()
