"""
backend/core/cache.py
Galaxy Vast AI — Two-Level Cache (in-process LRU + Redis)

P7-CACHE-1: LRU eviction when max_size exceeded
P7-CACHE-2: Redis serialisation via msgpack with fallback to json
P7-CACHE-3: key namespacing to prevent collisions across modules
P7-CACHE-4: async-safe in-process cache (no threading issues)
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# In-process LRU Cache
# --------------------------------------------------------------------------- #


class LRUCache:
    """
    Thread-safe LRU cache backed by an OrderedDict.

    Args:
        max_size: Maximum number of entries before LRU eviction.
        default_ttl: Default TTL in seconds (0 = no expiry).
    """

    def __init__(self, max_size: int = 1024, default_ttl: float = 300.0) -> None:
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._max = max_size
        self._ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._store:
                return None
            value, expiry = self._store[key]
            if expiry and time.monotonic() > expiry:
                del self._store[key]
                return None
            self._store.move_to_end(key)  # mark as recently used
            return value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
    ) -> None:
        async with self._lock:
            effective_ttl = ttl if ttl is not None else self._ttl
            expiry = (time.monotonic() + effective_ttl) if effective_ttl else 0.0
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (value, expiry)
            # P7-CACHE-1: LRU eviction
            while len(self._store) > self._max:
                oldest = next(iter(self._store))
                del self._store[oldest]
                logger.debug("[LRUCache] evicted key: %s", oldest)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    @property
    def size(self) -> int:
        return len(self._store)


# --------------------------------------------------------------------------- #
# Redis wrapper (optional)
# --------------------------------------------------------------------------- #


class RedisCache:
    """
    Thin async wrapper around aioredis with JSON serialisation fallback.
    P7-CACHE-2: tries msgpack first, falls back to json.
    """

    def __init__(self, redis_client: Any) -> None:
        self._r = redis_client

    def _serialise(self, value: Any) -> bytes:
        try:
            import msgpack

            return msgpack.packb(value, use_bin_type=True)
        except Exception:
            return json.dumps(value).encode()

    def _deserialise(self, data: bytes) -> Any:
        try:
            import msgpack

            return msgpack.unpackb(data, raw=False)
        except Exception:
            return json.loads(data)

    async def get(self, key: str) -> Optional[Any]:
        try:
            raw = await self._r.get(key)
            return self._deserialise(raw) if raw is not None else None
        except Exception as exc:
            logger.warning("[RedisCache] get error for %s: %s", key, exc)
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        try:
            data = self._serialise(value)
            if ttl:
                await self._r.setex(key, ttl, data)
            else:
                await self._r.set(key, data)
        except Exception as exc:
            logger.warning("[RedisCache] set error for %s: %s", key, exc)

    async def delete(self, key: str) -> bool:
        try:
            result = await self._r.delete(key)
            return bool(result)
        except Exception as exc:
            logger.warning("[RedisCache] delete error for %s: %s", key, exc)
            return False


# --------------------------------------------------------------------------- #
# Two-level cache facade
# --------------------------------------------------------------------------- #


class TwoLevelCache:
    """
    Combines an in-process LRUCache (L1) with an optional Redis cache (L2).

    P7-CACHE-3: all keys are namespaced with a module prefix.
    """

    def __init__(
        self,
        namespace: str = "galaxy",
        l1_size: int = 512,
        l1_ttl: float = 60.0,
        redis: Optional[Any] = None,
    ) -> None:
        self._ns = namespace
        self._l1 = LRUCache(max_size=l1_size, default_ttl=l1_ttl)
        self._l2 = RedisCache(redis) if redis else None

    def _key(self, key: str) -> str:
        return f"{self._ns}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        ns_key = self._key(key)
        # L1 hit
        value = await self._l1.get(ns_key)
        if value is not None:
            return value
        # L2 hit
        if self._l2:
            value = await self._l2.get(ns_key)
            if value is not None:
                await self._l1.set(ns_key, value)
                return value
        return None

    async def set(
        self,
        key: str,
        value: Any,
        l1_ttl: Optional[float] = None,
        l2_ttl: Optional[int] = None,
    ) -> None:
        ns_key = self._key(key)
        await self._l1.set(ns_key, value, ttl=l1_ttl)
        if self._l2:
            await self._l2.set(ns_key, value, ttl=l2_ttl)

    async def delete(self, key: str) -> None:
        ns_key = self._key(key)
        await self._l1.delete(ns_key)
        if self._l2:
            await self._l2.delete(ns_key)


# Module-level defaults
cache = TwoLevelCache(namespace="galaxy", l1_size=512, l1_ttl=60.0)
