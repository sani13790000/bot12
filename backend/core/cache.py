"""
Unified cache layer — Redis-backed with in-memory LRU fallback.

Usage:
    from backend.core.cache import cache
    result = await cache.get("key")
    await cache.set("key", value, ttl=30)
    await cache.delete("key")
    @cache.cached(ttl=30, key_prefix="analysis")
    async def my_func(symbol): ...
"""
from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# In-memory LRU+TTL cache (fallback when Redis unavailable)
# ──────────────────────────────────────────────

class _Entry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl

    @property
    def alive(self) -> bool:
        return time.monotonic() < self.expires_at


class _InMemoryLRU:
    """Thread-safe LRU cache with per-entry TTL."""

    def __init__(self, maxsize: int = 4096) -> None:
        self._maxsize = maxsize
        self._store: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if not entry.alive:
                del self._store[key]
                return None
            # LRU: move to end
            self._store.move_to_end(key)
            return entry.value

    async def set(self, key: str, value: Any, ttl: float = 60.0) -> None:
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = _Entry(value, ttl)
            # Evict oldest if over capacity
            while len(self._store) > self._maxsize:
                self._store.popitem(last=False)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    async def cleanup(self) -> int:
        """Remove expired entries. Returns count removed."""
        async with self._lock:
            now = time.monotonic()
            expired = [k for k, v in self._store.items() if v.expires_at <= now]
            for k in expired:
                del self._store[k]
            return len(expired)


# ──────────────────────────────────────────────
# Unified Cache — Redis primary, InMemory fallback
# ──────────────────────────────────────────────

class Cache:
    """Production cache: Redis-backed with automatic in-memory fallback."""

    def __init__(
        self,
        redis_url: str = "redis://redis:6379/0",
        maxsize: int = 4096,
        default_ttl: float = 60.0,
    ) -> None:
        self._redis_url = redis_url
        self._default_ttl = default_ttl
        self._local = _InMemoryLRU(maxsize=maxsize)
        self._redis: Any = None  # lazy
        self._redis_ok = False
        self._check_interval = 30.0
        self._last_check = 0.0

    # ── Redis lazy connect ──────────────────────

    async def _ensure_redis(self) -> bool:
        """Return True if Redis is usable. Re-probe every 30s after failure."""
        if self._redis_ok:
            return True
        now = time.monotonic()
        if now - self._last_check < self._check_interval:
            return False
        self._last_check = now
        try:
            import redis.asyncio as aioredis  # lazy import
            if self._redis is None:
                self._redis = await aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    max_connections=20,
                )
            await self._redis.ping()
            self._redis_ok = True
            logger.info("cache: Redis connected")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("cache: Redis unavailable (%s), using in-memory", exc)
            self._redis_ok = False
            return False

    def _serialize(self, value: Any) -> str:
        return json.dumps(value, default=str)

    def _deserialize(self, raw: str) -> Any:
        return json.loads(raw)

    # ── Public API ─────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        # 1. local L1
        local_val = await self._local.get(key)
        if local_val is not None:
            return local_val
        # 2. Redis L2
        if await self._ensure_redis():
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    val = self._deserialize(raw)
                    # backfill L1
                    await self._local.set(key, val, ttl=self._default_ttl)
                    return val
            except Exception as exc:  # noqa: BLE001
                logger.warning("cache.get Redis error: %s", exc)
                self._redis_ok = False
        return None

    async def set(
        self, key: str, value: Any, ttl: Optional[float] = None
    ) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        # L1
        await self._local.set(key, value, ttl=ttl)
        # L2
        if await self._ensure_redis():
            try:
                await self._redis.setex(key, int(ttl), self._serialize(value))
            except Exception as exc:  # noqa: BLE001
                logger.warning("cache.set Redis error: %s", exc)
                self._redis_ok = False

    async def delete(self, key: str) -> None:
        await self._local.delete(key)
        if await self._ensure_redis():
            try:
                await self._redis.delete(key)
            except Exception:  # noqa: BLE001
                pass

    async def clear_prefix(self, prefix: str) -> None:
        """Delete all keys starting with prefix (local + Redis)."""
        async with self._local._lock:
            to_del = [k for k in self._local._store if k.startswith(prefix)]
            for k in to_del:
                del self._local._store[k]
        if await self._ensure_redis():
            try:
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(
                        cursor, match=f"{prefix}*", count=200
                    )
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
            except Exception:  # noqa: BLE001
                pass

    # ── Decorator ──────────────────────────────

    def cached(
        self,
        ttl: float = 60.0,
        key_prefix: str = "",
    ) -> Callable:
        """Async function cache decorator.

        Usage::

            @cache.cached(ttl=30, key_prefix="analysis")
            async def get_analysis(symbol: str, tf: str) -> dict: ...
        """
        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                raw_key = f"{key_prefix}:{fn.__name__}:{args}:{sorted(kwargs.items())}"
                key = hashlib.sha256(raw_key.encode()).hexdigest()[:40]
                cached_val = await self.get(key)
                if cached_val is not None:
                    return cached_val
                result = await fn(*args, **kwargs)
                if result is not None:
                    await self.set(key, result, ttl=ttl)
                return result
            return wrapper
        return decorator

    async def start_cleanup_task(self) -> None:
        """Background cleanup of expired in-memory entries."""
        async def _loop() -> None:
            while True:
                await asyncio.sleep(120)
                removed = await self._local.cleanup()
                if removed:
                    logger.debug("cache: cleaned %d expired entries", removed)
        asyncio.create_task(_loop(), name="cache-cleanup")


# ── Singleton ──────────────────────────────────
cache = Cache()
