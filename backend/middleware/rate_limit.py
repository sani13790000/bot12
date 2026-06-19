"""
backend/middleware/rate_limit.py
Rate limiting middleware — Redis-backed with InMemory fallback.

Limits:
  - /api/v1/auth/login    : 5  req/min  per IP
  - /api/v1/auth/register : 3  req/min  per IP
  - /api/v1/auth/refresh  : 10 req/min  per IP
  - /ws/*                 : 20 conn/min per IP
  - All other endpoints   : 60 req/min  per IP

Security:
  - Sliding window algorithm
  - MAX_TRACKED_IPS eviction to prevent memory DoS
  - asyncio.Lock for thread safety
  - Redis prefix isolation
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MAX_TRACKED_IPS = 50_000
_REDIS_PREFIX = "rl:"

# (path_prefix, method_or_None) → (max_requests, window_seconds)
_RULES: List[Tuple[str, Optional[str], int, int]] = [
    ("/api/v1/auth/login",    "POST",  5,  60),
    ("/api/v1/auth/register", "POST",  3,  60),
    ("/api/v1/auth/refresh",  "POST",  10, 60),
    ("/ws/",                  None,    20, 60),
    ("/api/v1/backtest",      "POST",  10, 60),
    ("/api/v1/analysis",      "POST",  30, 60),
    ("/",                     None,    60, 60),   # catch-all
]


def _get_rule(path: str, method: str) -> Tuple[int, int]:
    """Return (max_requests, window_seconds) for the given path+method."""
    for prefix, rule_method, max_req, window in _RULES:
        if path.startswith(prefix):
            if rule_method is None or rule_method == method:
                return max_req, window
    return 60, 60  # default


# ---------------------------------------------------------------------------
# In-memory limiter (fallback when Redis is unavailable)
# ---------------------------------------------------------------------------

class _InMemoryLimiter:
    """Sliding window rate limiter using in-memory deques."""

    def __init__(self) -> None:
        self._windows: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def is_allowed(self, key: str, max_requests: int, window_sec: int) -> bool:
        async with self._lock:
            now = time.monotonic()
            window = self._windows[key]

            # Slide window
            cutoff = now - window_sec
            # Remove expired entries
            while window and window[0] < cutoff:
                window.pop(0)

            if len(window) >= max_requests:
                return False

            window.append(now)

            # Evict oldest IP if map is too large
            if len(self._windows) > _MAX_TRACKED_IPS:
                oldest_key = next(iter(self._windows))
                del self._windows[oldest_key]

            return True

    async def cleanup(self) -> None:
        """Remove empty/expired windows."""
        async with self._lock:
            now = time.monotonic()
            to_delete = [
                k for k, v in self._windows.items()
                if not v or now - v[-1] > 3600  # idle for 1 hour
            ]
            for k in to_delete:
                del self._windows[k]


_in_memory = _InMemoryLimiter()
_redis_client = None
_redis_lock = asyncio.Lock()


async def _get_redis():
    """Lazy Redis connection with thread-safe singleton."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis.asyncio as aioredis
            from backend.core.config import get_settings
            settings = get_settings()
            client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            await client.ping()
            _redis_client = client
            log.info("Rate limiter: Redis connected")
            return _redis_client
        except Exception as exc:
            log.warning("Rate limiter: Redis unavailable (%s), using in-memory", type(exc).__name__)
            return None


async def _redis_is_allowed(key: str, max_requests: int, window_sec: int) -> Optional[bool]:
    """Sliding window via Redis ZADD. Returns None if Redis unavailable."""
    try:
        redis = await _get_redis()
        if redis is None:
            return None

        redis_key = f"{_REDIS_PREFIX}{key}"
        now = time.time()
        cutoff = now - window_sec

        pipe = redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, cutoff)
        pipe.zcard(redis_key)
        pipe.zadd(redis_key, {str(now): now})
        pipe.expire(redis_key, window_sec + 1)
        results = await pipe.execute()

        count_before_add = results[1]
        return count_before_add < max_requests
    except Exception as exc:
        log.debug("Redis rate limit error: %s", type(exc).__name__)
        return None


async def _is_allowed(key: str, max_requests: int, window_sec: int) -> bool:
    """Check rate limit — Redis first, fallback to in-memory."""
    result = await _redis_is_allowed(key, max_requests, window_sec)
    if result is not None:
        return result
    return await _in_memory.is_allowed(key, max_requests, window_sec)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class RateLimitMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        # Determine client IP
        forwarded = request.headers.get("X-Forwarded-For", "")
        ip = forwarded.split(",")[0].strip() if forwarded else (
            request.client.host if request.client else "unknown"
        )

        path = request.url.path
        method = request.method

        max_req, window = _get_rule(path, method)
        rate_key = f"{ip}:{path}"

        allowed = await _is_allowed(rate_key, max_req, window)
        if not allowed:
            log.warning("Rate limit exceeded: ip=%s path=%s", ip, path)
            return JSONResponse(
                {
                    "detail": "Too many requests",
                    "retry_after": window,
                },
                status_code=429,
                headers={"Retry-After": str(window)},
            )

        return await call_next(request)


# ---------------------------------------------------------------------------
# Background cleanup task
# ---------------------------------------------------------------------------

async def start_cleanup_task() -> None:
    """Run every 5 minutes to evict stale in-memory windows."""
    while True:
        await asyncio.sleep(300)
        try:
            await _in_memory.cleanup()
        except Exception as exc:
            log.debug("Rate limit cleanup error: %s", exc)
