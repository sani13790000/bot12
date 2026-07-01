"""
backend/core/cache.py
Galaxy Vast AI — Two-Level Cache (Local LRU + Redis)

All Redis operations fail gracefully with local LRU fallback.
"""
from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

_LOG = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU cache with TTL."""

    def __init__(self, maxsize: int = 1000, default_ttl: float = 300.0) -> None:
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._store: OrderedDict = OrderedDict()
        self._expiry: dict = {}

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        if time.time() > self._expiry.get(key, float('inf')):
            del self._store[key]
            del self._expiry[key]
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        self._expiry[key] = time.time() + (ttl or self._default_ttl)
        if len(self._store) > self._maxsize:
            oldest = next(iter(self._store))
            del self._store[oldest]
            self._expiry.pop(oldest, None)

    def delete(self, key: str) -> bool:
        if key in self._store:
            del self._store[key]
            self._expiry.pop(key, None)
            return True
        return False

    def clear(self) -> None:
        self._store.clear()
        self._expiry.clear()

    def __len__(self) -> int:
        return len(self._store)


class TwoLevelCache:
    """Local LRU + optional Redis backend."""

    def __init__(self, local_maxsize: int = 1000, local_ttl: float = 60.0,
                 redis_url: Optional[str] = None) -> None:
        self._local = LRUCache(maxsize=local_maxsize, default_ttl=local_ttl)
        self._redis = None
        if redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(redis_url)
            except ImportError:
                _LOG.debug('redis not installed, using local cache only')

    async def get(self, key: str) -> Optional[Any]:
        val = self._local.get(key)
        if val is not None:
            return val
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    return json.loads(raw)
            except Exception as e:
                _LOG.debug('Redis get failed: %s', e)
        return None

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        self._local.set(key, value, ttl)
        if self._redis:
            try:
                await self._redis.set(key, json.dumps(value, default=str), ex=int(ttl or 60))
            except Exception as e:
                _LOG.debug('Redis set failed: %s', e)

    async def delete(self, key: str) -> None:
        self._local.delete(key)
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as e:
                _LOG.debug('Redis delete failed: %s', e)


_cache: Optional[TwoLevelCache] = None


def get_cache() -> TwoLevelCache:
    global _cache
    if _cache is None:
        import os
        _cache = TwoLevelCache(redis_url=os.environ.get('REDIS_URL'))
    return _cache
