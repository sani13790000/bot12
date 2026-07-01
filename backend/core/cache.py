"""
backend/core/cache.py
Galaxy Vast AI — Two-Level Cache (Local LRU + Redis)

All Redis operations are wrapped so the app works without Redis installed.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)
__all__ = ["Cache", "get_cache", "cache_result"]


class _LRUCache:
    """Simple thread-unsafe LRU cache."""
    def __init__(self, maxsize: int = 1000) -> None:
        self._store: OrderedDict[str, tuple] = OrderedDict()
        self._maxsize = maxsize

    def get(self, key: str) -> Optional[Any]:
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if expires_at and time.time() > expires_at:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expires_at = time.time() + ttl if ttl else None
        self._store[key] = (value, expires_at)
        self._store.move_to_end(key)
        if len(self._store) > self._maxsize:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


class Cache:
    """Two-level cache: local LRU + optional Redis."""

    def __init__(self, redis_url: Optional[str] = None, local_maxsize: int = 1000) -> None:
        self._local = _LRUCache(maxsize=local_maxsize)
        self._redis: Any = None
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                logger.info("Redis cache connected: %s", redis_url)
            except Exception as exc:
                logger.warning("Redis unavailable (%s) — local-only cache", exc)
                self._redis = None

    def get(self, key: str) -> Optional[Any]:
        val = self._local.get(key)
        if val is not None:
            return val
        if self._redis:
            try:
                raw = self._redis.get(key)
                if raw:
                    val = json.loads(raw)
                    self._local.set(key, val)
                    return val
            except Exception:
                pass
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = 300) -> None:
        self._local.set(key, value, ttl=ttl)
        if self._redis:
            try:
                self._redis.setex(key, ttl or 300, json.dumps(value, default=str))
            except Exception:
                pass

    def delete(self, key: str) -> None:
        self._local.delete(key)
        if self._redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass

    def clear(self) -> None:
        self._local.clear()


_cache: Optional[Cache] = None

def get_cache() -> Cache:
    global _cache
    if _cache is None:
        import os
        _cache = Cache(redis_url=os.environ.get("REDIS_URL"))
    return _cache


def cache_result(key_prefix: str, ttl: int = 300):
    """Decorator: cache function result."""
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = key_prefix + ":" + hashlib.md5(
                json.dumps((args, kwargs), default=str).encode()
            ).hexdigest()[:12]
            cache = get_cache()
            cached = cache.get(key)
            if cached is not None:
                return cached
            result = fn(*args, **kwargs)
            cache.set(key, result, ttl=ttl)
            return result
        return wrapper
    return decorator
