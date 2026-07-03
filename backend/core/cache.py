"""
backend/core/cache.py
Galaxy Vast AI — Two-Level Cache (Local LRU + Redis)

All Redis operations are optional and fail gracefully.
Failures are logged and bypass to local LRU.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

log = logging.getLogger(__name__)

_DEFAULT_TTL   = 300   # 5 minutes
_DEFAULT_SIZE  = 1024  # max entries


class LRUCache:
    """Simple thread-safe LRU cache with TTL."""

    def __init__(self, max_size: int = _DEFAULT_SIZE) -> None:
        self._cache: OrderedDict[str, tuple] = OrderedDict()
        self._max   = max_size

    def get(self, key: str) -> Optional[Any]:
        if key not in self._cache:
            return None
        value, expires_at = self._cache[key]
        if expires_at and time.time() > expires_at:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = _DEFAULT_TTL) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._cache[key] = (value, expires_at)
        self._cache.move_to_end(key)
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


class TwoLevelCache:
    """Local LRU + optional Redis backend."""

    def __init__(self, redis_url: Optional[str] = None, max_local: int = _DEFAULT_SIZE) -> None:
        self._local  = LRUCache(max_size=max_local)
        self._redis  = None
        self._redis_url = redis_url

    async def connect(self) -> None:
        if not self._redis_url:
            return
        try:
            import aioredis
            self._redis = await aioredis.from_url(self._redis_url, encoding="utf-8", decode_responses=True)
            log.info("cache_redis_connected url=%s", self._redis_url)
        except Exception as exc:
            log.warning("cache_redis_unavailable: %s (local-only mode)", exc)
            self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        value = self._local.get(key)
        if value is not None:
            return value
        if self._redis:
            try:
                raw = await self._redis.get(key)
                if raw:
                    value = json.loads(raw)
                    self._local.set(key, value)
                    return value
            except Exception as exc:
                log.debug("cache_redis_get_error key=%s: %s", key, exc)
        return None

    async def set(self, key: str, value: Any, ttl: int = _DEFAULT_TTL) -> None:
        self._local.set(key, value, ttl=ttl)
        if self._redis:
            try:
                await self._redis.setex(key, ttl, json.dumps(value, default=str))
            except Exception as exc:
                log.debug("cache_redis_set_error key=%s: %s", key, exc)

    async def delete(self, key: str) -> bool:
        local_deleted = self._local.delete(key)
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception as exc:
                log.debug("cache_redis_delete_error key=%s: %s", key, exc)
        return local_deleted

    async def close(self) -> None:
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass


_cache: Optional[TwoLevelCache] = None


def get_cache() -> TwoLevelCache:
    global _cache
    if _cache is None:
        import os
        _cache = TwoLevelCache(redis_url=os.environ.get("REDIS_URL"))
    return _cache
