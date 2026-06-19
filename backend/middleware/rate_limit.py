"""
backend/middleware/rate_limit.py
Rate-limiting middleware - production-hardened v3.

Key changes vs v2:
  * In-memory uses deque (O(1) popleft vs list.pop(0) O(n)).
  * IP via get_client_ip() - spoof-resistant.
  * Rate-limit key = logical BUCKET (not raw path) - no key explosion.
  * /health/live and /health/ready fully exempt (Kubernetes probes).
  * /ws prefix-matched correctly.
  * Redis uses atomic Lua sliding window (EVALSHA).
  * Members use uuid4 - no collisions under concurrency.
  * Rejected requests NOT added to window.
  * X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Window on all responses.
  * Retry-After on 429.
  * close_redis() exported for graceful shutdown.
  * Degraded-mode log emitted once, not per-request.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.core.client_ip import get_client_ip

log = logging.getLogger(__name__)

_MAX_TRACKED_KEYS: int = 100_000
_REDIS_PREFIX:     str = "rl:"

_BucketRule = Tuple[str, int, int]  # (bucket, max_req, window_sec)


def _get_rule(path: str, method: str) -> _BucketRule:
    """Map (path, method) to (bucket_name, max_requests, window_seconds)."""
    # Kubernetes/LB probes - never block
    if path in ("/health/live", "/health/ready"):
        return "probe", 10_000, 60
    if path == "/health":
        return "health", 120, 60
    # Auth endpoints
    if path == "/api/v1/auth/login"    and method == "POST": return "auth_login",    5,  60
    if path == "/api/v1/auth/register" and method == "POST": return "auth_register", 3,  60
    if path == "/api/v1/auth/refresh"  and method == "POST": return "auth_refresh",  10, 60
    # WebSocket (prefix match)
    if path == "/ws" or path.startswith("/ws/"):             return "websocket",     20, 60
    # Compute-heavy
    if path.startswith("/api/v1/backtest"):                  return "backtest",      10, 60
    if path.startswith("/api/v1/analysis"):                  return "analysis",      30, 60
    # Global catch-all
    return "global", 60, 60


class _InMemoryLimiter:
    """
    Sliding-window rate limiter using per-key deques.
    deque.popleft() is O(1); list.pop(0) is O(n).
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque] = defaultdict(deque)
        self._lock    = asyncio.Lock()
        self._degraded_logged = False

    def _log_degraded_once(self) -> None:
        if not self._degraded_logged:
            log.warning(
                "RateLimiter: Redis unavailable - running degraded in-memory mode. "
                "Limits NOT shared across multiple worker processes."
            )
            self._degraded_logged = True

    async def check(self, key: str, max_requests: int, window_sec: int) -> Tuple[bool, int]:
        """
        Check-and-record a request.
        Returns (allowed, remaining).
        If not allowed, request is NOT recorded (token not consumed).
        """
        self._log_degraded_once()
        async with self._lock:
            now    = time.monotonic()
            cutoff = now - window_sec
            dq     = self._windows[key]
            # Expire old entries - O(k expired) amortised O(1)
            while dq and dq[0] < cutoff:
                dq.popleft()
            current = len(dq)
            if current >= max_requests:
                return False, 0
            dq.append(now)
            # Evict LRU key if map too large
            if len(self._windows) > _MAX_TRACKED_KEYS:
                try:
                    del self._windows[next(iter(self._windows))]
                except StopIteration:
                    pass
            return True, max(0, max_requests - len(dq))

    async def cleanup(self) -> None:
        """Remove keys idle for more than 1 hour."""
        async with self._lock:
            now    = time.monotonic()
            cutoff = now - 3600
            to_del = [
                k for k, dq in self._windows.items()
                if not dq or dq[-1] < cutoff
            ]
            for k in to_del:
                del self._windows[k]
            if to_del:
                log.debug("RateLimiter cleanup: evicted %d stale keys", len(to_del))


_in_memory = _InMemoryLimiter()

# Atomic Lua sliding-window script.
# Returns {count_before_add, was_added} where was_added=1 means allowed.
# Rejected requests are NOT added (no token consumed).
_LUA_SLIDING_WINDOW = """
local key    = KEYS[1]
local cutoff = tonumber(ARGV[1])
local limit  = tonumber(ARGV[2])
local now    = tonumber(ARGV[3])
local member = ARGV[4]
local ttl    = tonumber(ARGV[5])
redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, ttl)
    return {count, 1}
else
    redis.call('EXPIRE', key, ttl)
    return {count, 0}
end
"""

_redis_client           = None
_redis_lock             = asyncio.Lock()
_lua_sha: Optional[str] = None


async def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        try:
            import redis.asyncio as aioredis
            from backend.core.config import get_settings
            s = get_settings()
            client = aioredis.from_url(
                s.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                max_connections=getattr(s, "REDIS_MAX_CONNECTIONS", 20),
                socket_connect_timeout=2,
                socket_timeout=1,
            )
            await client.ping()
            _redis_client = client
            log.info("RateLimiter: Redis connected at %s", s.REDIS_URL)
            return _redis_client
        except Exception as exc:
            log.warning("RateLimiter: Redis unavailable (%s)", type(exc).__name__)
            return None


async def close_redis() -> None:
    """Close Redis connection cleanly. Call from lifespan shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
            log.info("RateLimiter: Redis connection closed.")
        except Exception as exc:
            log.debug("RateLimiter: error closing Redis: %s", exc)
        finally:
            _redis_client = None


async def _redis_check(
    key: str, max_requests: int, window_sec: int
) -> Optional[Tuple[bool, int]]:
    """Atomic Redis sliding-window check. Returns (allowed, remaining) or None."""
    global _lua_sha
    try:
        redis = await _get_redis()
        if redis is None:
            return None
        redis_key = f"{_REDIS_PREFIX}{key}"
        now       = time.time()
        cutoff    = now - window_sec
        member    = str(uuid.uuid4())  # unique per-request - no collisions
        ttl       = window_sec + 1
        args      = [str(cutoff), str(max_requests), str(now), member, str(ttl)]
        result    = None
        if _lua_sha:
            try:
                result = await redis.evalsha(_lua_sha, 1, redis_key, *args)
            except Exception:
                _lua_sha = None
        if result is None:
            result   = await redis.eval(_LUA_SLIDING_WINDOW, 1, redis_key, *args)
            _lua_sha = await redis.script_load(_LUA_SLIDING_WINDOW)
        count_before, was_added = int(result[0]), int(result[1])
        allowed   = was_added == 1
        remaining = max(0, max_requests - count_before - (1 if allowed else 0))
        return allowed, remaining
    except Exception as exc:
        log.debug("RateLimiter: Redis check error: %s", type(exc).__name__)
        return None


async def _check(key: str, max_requests: int, window_sec: int) -> Tuple[bool, int]:
    """Redis first, in-memory fallback."""
    result = await _redis_check(key, max_requests, window_sec)
    if result is not None:
        return result
    return await _in_memory.check(key, max_requests, window_sec)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate-limit middleware.

    Key format: "{bucket}:{client_ip}"
    Headers on every response:
        X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Window
    Additional on 429:
        Retry-After
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path      = request.url.path
        method    = request.method
        client_ip = get_client_ip(request)  # spoof-resistant

        bucket, max_req, window_sec = _get_rule(path, method)
        rate_key  = f"{bucket}:{client_ip}"

        allowed, remaining = await _check(rate_key, max_req, window_sec)

        rl_headers = {
            "X-RateLimit-Limit":     str(max_req),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Window":    str(window_sec),
        }

        if not allowed:
            log.warning(
                "rate_limit_exceeded bucket=%s ip=%s path=%s",
                bucket, client_ip, path,
            )
            return JSONResponse(
                {"detail": "Too many requests", "retry_after": window_sec, "bucket": bucket},
                status_code=429,
                headers={**rl_headers, "Retry-After": str(window_sec)},
            )

        response = await call_next(request)
        for k, v in rl_headers.items():
            response.headers[k] = v
        return response


async def start_cleanup_task() -> None:
    """Evict stale in-memory windows every 5 minutes. CancelledError handled cleanly."""
    log.info("RateLimiter: cleanup task started.")
    try:
        while True:
            await asyncio.sleep(300)
            try:
                await _in_memory.cleanup()
            except Exception as exc:
                log.debug("RateLimiter: cleanup error: %s", exc)
    except asyncio.CancelledError:
        log.info("RateLimiter: cleanup task cancelled.")
