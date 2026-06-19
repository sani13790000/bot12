"""
backend/middleware/rate_limit.py
Rate-limiting middleware — production-hardened.

Fix applied:
- Added _dynamic_ip_limits dict and reduce_rate_limit_for_ip() function
  which self_healing_service.py references but was missing → AttributeError
- All existing logic preserved
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.core.client_ip import get_client_ip

log = logging.getLogger(__name__)

_MAX_TRACKED_KEYS: int = 100_000
_REDIS_PREFIX:     str = "rl:"
_BucketRule = Tuple[str, int, int]  # (bucket, max_req, window_sec)

# ---------------------------------------------------------------------------
# Dynamic per-IP rate limit overrides (used by SelfHealingService)
# ---------------------------------------------------------------------------
# Maps IP address → (max_requests_override, expires_at_monotonic)
_dynamic_ip_limits: Dict[str, Tuple[int, float]] = {}
_dynamic_lock = asyncio.Lock()


async def reduce_rate_limit_for_ip(
    ip: str,
    factor: float = 0.5,
    duration_sec: int = 300,
    bucket_default_max: int = 60,
) -> None:
    """
    Temporarily reduce rate limit for a specific IP.
    Called by SelfHealingService on anomaly detection.

    Args:
        ip: IP address to throttle
        factor: multiply default limit by this (0.25 = 25% of normal)
        duration_sec: how long the restriction lasts
        bucket_default_max: baseline max_requests to apply factor against
    """
    new_max = max(1, int(bucket_default_max * factor))
    expires = time.monotonic() + duration_sec
    async with _dynamic_lock:
        _dynamic_ip_limits[ip] = (new_max, expires)
    log.warning(
        "rate_limit_reduced ip=%s new_max=%d duration=%ds factor=%.2f",
        ip, new_max, duration_sec, factor,
    )


async def remove_rate_limit_override(ip: str) -> None:
    """Remove dynamic rate limit override for an IP (e.g. after unblock)."""
    async with _dynamic_lock:
        _dynamic_ip_limits.pop(ip, None)


async def _get_dynamic_override(ip: str) -> Optional[int]:
    """Return active max_requests override for IP, or None if expired/absent."""
    async with _dynamic_lock:
        entry = _dynamic_ip_limits.get(ip)
        if entry is None:
            return None
        max_req, expires = entry
        if time.monotonic() > expires:
            _dynamic_ip_limits.pop(ip, None)
            return None
        return max_req


def _get_rule(path: str, method: str) -> _BucketRule:
    """Map (path, method) → (bucket_name, max_requests, window_seconds)."""
    if path in ("/health/live", "/health/ready"):
        return "probe", 10_000, 60
    if path == "/health":
        return "health", 120, 60
    if path == "/api/v1/auth/login"    and method == "POST": return "auth_login",    5,  60
    if path == "/api/v1/auth/register" and method == "POST": return "auth_register", 3,  60
    if path == "/api/v1/auth/refresh"  and method == "POST": return "auth_refresh",  10, 60
    if path == "/ws" or path.startswith("/ws/"):             return "websocket",     20, 60
    if path.startswith("/api/v1/backtest"):                  return "backtest",      10, 60
    if path.startswith("/api/v1/analysis"):                  return "analysis",      30, 60
    return "global", 60, 60


class _InMemoryLimiter:
    """Sliding-window rate limiter using per-key deques (O(1) popleft)."""

    def __init__(self) -> None:
        self._windows: Dict[str, deque] = defaultdict(deque)
        self._lock    = asyncio.Lock()
        self._degraded_logged = False

    def _log_degraded_once(self) -> None:
        if not self._degraded_logged:
            log.warning(
                "RateLimiter: Redis unavailable — in-memory mode active. "
                "Limits NOT shared across multiple worker processes."
            )
            self._degraded_logged = True

    async def check(self, key: str, max_requests: int, window_sec: int) -> Tuple[bool, int]:
        self._log_degraded_once()
        async with self._lock:
            now    = time.monotonic()
            cutoff = now - window_sec
            dq     = self._windows[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            current = len(dq)
            if current >= max_requests:
                return False, 0
            dq.append(now)
            if len(self._windows) > _MAX_TRACKED_KEYS:
                try:
                    del self._windows[next(iter(self._windows))]
                except StopIteration:
                    pass
            return True, max(0, max_requests - len(dq))

    async def cleanup(self) -> None:
        async with self._lock:
            now    = time.monotonic()
            cutoff = now - 3600
            to_del = [k for k, dq in self._windows.items() if not dq or dq[-1] < cutoff]
            for k in to_del:
                del self._windows[k]
            if to_del:
                log.debug("RateLimiter cleanup: evicted %d stale keys", len(to_del))


_in_memory = _InMemoryLimiter()

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
    """Close Redis cleanly. Call from lifespan shutdown."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
            log.info("RateLimiter: Redis closed.")
        except Exception as exc:
            log.debug("RateLimiter: error closing Redis: %s", exc)
        finally:
            _redis_client = None


async def _redis_check(key: str, max_requests: int, window_sec: int) -> Optional[Tuple[bool, int]]:
    global _lua_sha
    try:
        redis = await _get_redis()
        if redis is None:
            return None
        redis_key = f"{_REDIS_PREFIX}{key}"
        now       = time.time()
        cutoff    = now - window_sec
        member    = str(uuid.uuid4())
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
    result = await _redis_check(key, max_requests, window_sec)
    if result is not None:
        return result
    return await _in_memory.check(key, max_requests, window_sec)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate-limit middleware.
    Supports dynamic per-IP overrides via _dynamic_ip_limits.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path      = request.url.path
        method    = request.method
        client_ip = get_client_ip(request)

        bucket, max_req, window_sec = _get_rule(path, method)

        # Apply dynamic per-IP override if active
        override = await _get_dynamic_override(client_ip)
        if override is not None:
            max_req = override

        rate_key = f"{bucket}:{client_ip}"
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
    """Evict stale in-memory windows + expired dynamic overrides every 5 min."""
    log.info("RateLimiter: cleanup task started.")
    try:
        while True:
            await asyncio.sleep(300)
            try:
                await _in_memory.cleanup()
                # Cleanup expired dynamic overrides
                async with _dynamic_lock:
                    now = time.monotonic()
                    expired = [ip for ip, (_, exp) in _dynamic_ip_limits.items() if now > exp]
                    for ip in expired:
                        del _dynamic_ip_limits[ip]
                    if expired:
                        log.debug("RateLimiter: evicted %d expired IP overrides", len(expired))
            except Exception as exc:
                log.warning("RateLimiter: cleanup error: %s", exc)
    except asyncio.CancelledError:
        log.info("RateLimiter: cleanup task cancelled.")
