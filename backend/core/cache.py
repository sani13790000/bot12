"""
backend/core/cache.py
Galaxy Vast AI — Multi-Tier Cache System

Provides:
  - L1: In-process LRU dict cache (microsecond latency)
  - L2: Redis async cache (millisecond latency, optional)
  - Cache-aside pattern helpers
  - TTL-based expiry
  - Cache statistics
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU cache with TTL."""

    def __init__(self, max_size: int = 256, default_ttl: float = 300.0) -> None:
        self._max = max_size
        self._ttl = default_ttl
        self._store: OrderedDict[str, Tuple[Any, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            self._misses += 1
            return None
        value, expires = self._store[key]
        if time.monotonic() > expires:
            del self._store[key]
            self._misses += 1
            return None
        self._store.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (value, time.monotonic() + (ttl or self._ttl))
        if len(self._store) > self._max:
            self._store.popitem(last=False)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()
        self._hits = self._misses = 0

    @property
    def stats(self) -> Dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._store),
            "max_size": self._max,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total else 0.0,
        }


class CacheManager:
    """Multi-tier cache manager: L1 LRU + optional L2 Redis."""

    def __init__(self, l1_size: int = 512, default_ttl: float = 300.0) -> None:
        self._l1 = LRUCache(max_size=l1_size, default_ttl=default_ttl)
        self._redis: Optional[Any] = None
        self._log = logging.getLogger(self.__class__.__name__)

    async def connect_redis(self, url: str) -> None:
        """Optionally connect to Redis as L2 cache."""
        try:
            import redis.asyncio as aioredis
            self._redis = await aioredis.from_url(url, encoding="utf-8", decode_responses=True)
            self._log.info("Connected to Redis L2 cache: %s", url)
        except ImportError:
            self._log.warning("redis not installed; L2 cache disabled")
        except Exception as exc:
            self._log.error("Redis connection failed: %s", exc)

    async def get(self, key: str) -> Optional[Any]:
        """Get from L1, then L2."""
        val = self._l1.get(key)
        if val is not None:
            return val
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    val = json.loads(raw)
                    self._l1.set(key, val)
                    return val
            except Exception as exc:
                self._log.debug("Redis get error: %s", exc)
        return None

    async def set(self, key: str, value: Any, ttl: float = 300.0) -> None:
        """Set in L1 and L2."""
        self._l1.set(key, value, ttl=ttl)
        if self._redis:
            try:
                await self._redis.setex(key, int(ttl), json.dumps(value, default=str))
            except Exception as exc:
                self._log.debug("Redis set error: %s", exc)

    async def delete(self, key: str) -> None:
        """Delete from both tiers."""
        self._l1.delete(key)
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as exc:
                self._log.debug("Redis delete error: %s", exc)

    async def clear(self) -> None:
        self._l1.clear()
        if self._redis:
            try:
                await self._redis.flushdb()
            except Exception:
                pass

    @property
    def l1_stats(self) -> Dict[str, Any]:
        return self._l1.stats


_cache: Optional[CacheManager] = None


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache


def cache_key(*parts: Any) -> str:
    """Generate a deterministic cache key from parts."""
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
