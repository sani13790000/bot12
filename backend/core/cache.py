"""
backend/core/cache.py
Galaxy Vast AI — Cache Layer (repaired)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    hits: int = 0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class InMemoryCache:
    def __init__(self, default_ttl: float = 300.0, max_size: int = 10_000) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._store[key]
            return None
        entry.hits += 1
        return entry.value

    async def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        async with self._lock:
            if len(self._store) >= self._max_size:
                self._evict()
            self._store[key] = CacheEntry(value=value, expires_at=time.time() + ttl)

    async def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def _evict(self) -> None:
        expired = [k for k, v in self._store.items() if v.is_expired()]
        for k in expired:
            del self._store[k]
        if len(self._store) >= self._max_size:
            lru = sorted(self._store, key=lambda k: self._store[k].hits)[:self._max_size // 4]
            for k in lru:
                del self._store[k]

    def stats(self) -> dict[str, Any]:
        now = time.time()
        active = sum(1 for e in self._store.values() if not e.is_expired())
        return {"total": len(self._store), "active": active, "max_size": self._max_size}


_cache: InMemoryCache | None = None


def get_cache() -> InMemoryCache:
    global _cache
    if _cache is None:
        _cache = InMemoryCache()
    return _cache


__all__ = ["InMemoryCache", "CacheEntry", "get_cache"]
