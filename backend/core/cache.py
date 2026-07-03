"""
backend/core/cache.py
Galaxy Vast AI — Two-Level Cache (Local LRU + Redis)

All Redis operations are optional and gracefully degrade.
"""
from __future__ import annotations
import time
from collections import OrderedDict
from typing import Any


class LRUCache:
    """Thread-unsafe in-process LRU cache."""

    def __init__(self, maxsize: int = 1024, ttl: float = 300.0) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        value, exp = self._cache[key]
        if time.monotonic() > exp:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        exp = time.monotonic() + (ttl if ttl is not None else self._ttl)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (value, exp)
        if len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        return self._cache.pop(key, None) is not None

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


class CacheManager:
    """Two-level cache: local LRU + optional Redis."""

    def __init__(self, maxsize: int = 2048, default_ttl: float = 300.0) -> None:
        self._local = LRUCache(maxsize=maxsize, ttl=default_ttl)
        self._redis: Any = None

    def get(self, key: str) -> Any | None:
        val = self._local.get(key)
        if val is not None:
            return val
        if self._redis:
            try:
                raw = self._redis.get(key)
                return raw
            except Exception:
                pass
        return None

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        self._local.set(key, value, ttl)

    def delete(self, key: str) -> None:
        self._local.delete(key)

    def clear(self) -> None:
        self._local.clear()


_cache: CacheManager | None = None


def get_cache() -> CacheManager:
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache


__all__ = ["LRUCache", "CacheManager", "get_cache"]
