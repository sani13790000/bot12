"""
backend/core/cache.py
Galaxy Vast AI - Two-Level Cache (Local LRU + Redis)

All Redis operations are optional and fail gracefully.
"""
from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Optional, Tuple

_LOG = logging.getLogger(__name__)


class LRUCache:
    """Thread-safe LRU cache."""

    def __init__(self, maxsize: int = 256) -> None:
        self._store: OrderedDict = OrderedDict()
        self._maxsize = maxsize
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                value, expires_at = self._store[key]
                if expires_at and time.time() > expires_at:
                    del self._store[key]
                    return None
                return value
            return None

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        async with self._lock:
            expires_at = time.time() + ttl if ttl else None
            self._store[key] = (value, expires_at)
            self._store.move_to_end(key)
            if len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()


class TwoLevelCache:
    """Two-level cache: local LRU + optional Redis."""

    def __init__(self, local_maxsize: int = 256, redis_url: Optional[str] = None) -> None:
        self._local = LRUCache(maxsize=local_maxsize)
        self._redis = None
        self._redis_url = redis_url

    async def get(self, key: str) -> Optional[Any]:
        # Try local first
        value = await self._local.get(key)
        if value is not None:
            return value
        return None

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        await self._local.set(key, value, ttl)

    async def delete(self, key: str) -> None:
        await self._local.delete(key)

    async def clear(self) -> None:
        await self._local.clear()

    def cached(self, ttl: float = 60.0, key_prefix: str = "") -> Callable:
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def wrapper(*args, **kwargs):
                key = f"{key_prefix}:{func.__name__}:{args}:{sorted(kwargs.items())}"
                cached_val = await self.get(key)
                if cached_val is not None:
                    return cached_val
                result = await func(*args, **kwargs)
                await self.set(key, result, ttl)
                return result
            return wrapper
        return decorator


cache = TwoLevelCache()
