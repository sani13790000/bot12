"""Rate-limiting middleware — Redis-backed with in-memory fallback.

Fixes applied:
- Added MAX_TRACKED_IPS cap to InMemoryRateLimiter._windows to prevent OOM
  during DDoS / mass IP attacks
- Cleanup task evicts expired entries every 5 minutes
- Per-path rules: /auth/login -> 5 req/min (brute-force protection)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# Maximum distinct IPs tracked in memory (prevents unbounded growth under DDoS)
MAX_TRACKED_IPS = 50_000
# Per-path rate-limit overrides: (max_requests, window_seconds)
_PATH_RULES: Dict[str, Tuple[int, int]] = {
    "/api/v1/auth/login": (5, 60),
    "/api/v1/auth/register": (10, 60),
    "/api/v1/auth/refresh": (20, 60),
}
_DEFAULT_RULE: Tuple[int, int] = (60, 60)  # 60 req / 60s


# ---------------------------------------------------------------------------
# In-memory limiter (sliding window)
# ---------------------------------------------------------------------------

class InMemoryRateLimiter:
    """Per-IP sliding-window rate limiter with bounded memory usage."""

    def __init__(self) -> None:
        # key: f"{ip}:{path}"  value: deque of timestamps
        self._windows: Dict[str, Deque[float]] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop(), name="rate_limit_cleanup")

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            now = time.monotonic()
            expired_keys = [
                k for k, dq in self._windows.items()
                if not dq or now - dq[-1] > 120  # no request in last 2 min
            ]
            for k in expired_keys:
                del self._windows[k]
            if expired_keys:
                logger.debug("Rate-limit cleanup: evicted %d expired keys.", len(expired_keys))

    def is_allowed(self, ip: str, path: str, max_req: int, window_sec: int) -> Tuple[bool, int, int]:
        """Returns (allowed, remaining, retry_after_sec)."""
        key = f"{ip}:{path}"
        now = time.monotonic()
        cutoff = now - window_sec

        dq = self._windows.get(key)
        if dq is None:
            # Enforce cap before creating a new entry
            if len(self._windows) >= MAX_TRACKED_IPS:
                # Evict oldest entry (FIFO)
                oldest_key = next(iter(self._windows))
                del self._windows[oldest_key]
                logger.warning("Rate-limit: MAX_TRACKED_IPS reached, evicted %s", oldest_key)
            dq = deque()
            self._windows[key] = dq

        # Remove timestamps outside the window
        while dq and dq[0] < cutoff:
            dq.popleft()

        remaining = max(0, max_req - len(dq))
        if len(dq) >= max_req:
            retry_after = int(window_sec - (now - dq[0])) + 1 if dq else window_sec
            return False, 0, retry_after

        dq.append(now)
        return True, remaining - 1, 0


# ---------------------------------------------------------------------------
# Redis limiter
# ---------------------------------------------------------------------------

class RedisRateLimiter:
    """Redis-backed sliding-window rate limiter using sorted sets."""

    def __init__(self, redis_url: str = "redis://redis:6379/0") -> None:
        self._url = redis_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client

    async def is_allowed(
        self, ip: str, path: str, max_req: int, window_sec: int
    ) -> Tuple[bool, int, int]:
        try:
            r = await self._get_client()
            key = f"rl:{ip}:{path}"
            now = time.time()
            cutoff = now - window_sec
            async with r.pipeline(transaction=True) as pipe:
                pipe.zremrangebyscore(key, "-inf", cutoff)
                pipe.zcard(key)
                pipe.zadd(key, {str(now): now})
                pipe.expire(key, window_sec + 1)
                results = await pipe.execute()
            count_before = results[1]
            if count_before >= max_req:
                oldest = await r.zrange(key, 0, 0, withscores=True)
                retry_after = int(window_sec - (now - oldest[0][1])) + 1 if oldest else window_sec
                return False, 0, retry_after
            return True, max(0, max_req - count_before - 1), 0
        except Exception as exc:  # noqa: BLE001
            logger.warning("Redis rate limiter error: %s — allowing request.", exc)
            return True, max_req, 0


# ---------------------------------------------------------------------------
# Singleton limiter instances
# ---------------------------------------------------------------------------

_memory_limiter: Optional[InMemoryRateLimiter] = None
_redis_limiter: Optional[RedisRateLimiter] = None
_limiter_lock = asyncio.Lock()


async def _get_limiter() -> InMemoryRateLimiter | RedisRateLimiter:
    """Return Redis limiter if available, else InMemory."""
    global _memory_limiter, _redis_limiter

    # Try Redis first
    if _redis_limiter is None:
        async with _limiter_lock:
            if _redis_limiter is None:
                import os
                redis_url = os.environ.get("REDIS_URL", "redis://redis:6379/0")
                _redis_limiter = RedisRateLimiter(redis_url)

    # Ensure memory limiter is running
    if _memory_limiter is None:
        async with _limiter_lock:
            if _memory_limiter is None:
                _memory_limiter = InMemoryRateLimiter()
                _memory_limiter.start()

    # Test Redis availability
    try:
        ok, _, _ = await _redis_limiter.is_allowed("probe", "/", 10000, 60)
        return _redis_limiter
    except Exception:  # noqa: BLE001
        return _memory_limiter


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Apply per-path rate limits; return 429 with Retry-After on breach."""

    _SKIP_PATHS: frozenset[str] = frozenset(["/health", "/", "/docs", "/openapi.json", "/ws/health"])

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if path in self._SKIP_PATHS or path.startswith("/ws/"):
            return await call_next(request)

        ip = request.client.host if request.client else "0.0.0.0"
        max_req, window_sec = _PATH_RULES.get(path, _DEFAULT_RULE)

        limiter = await _get_limiter()

        if isinstance(limiter, RedisRateLimiter):
            allowed, remaining, retry_after = await limiter.is_allowed(ip, path, max_req, window_sec)
        else:
            allowed, remaining, retry_after = limiter.is_allowed(ip, path, max_req, window_sec)

        if not allowed:
            logger.warning("Rate limit exceeded: ip=%s path=%s", ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests", "retry_after": retry_after},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(window_sec),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(window_sec)
        return response
