"""
backend/middleware/rate_limit.py
CRIT-A FIX: lazy asyncio.Lock init (Python 3.12+ safe)
Phase S additions: WebSocketRateLimiter, BurstAwareLimiter, extract_real_ip
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Callable, Dict, Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger("middleware.rate_limit")

_dynamic_ip_limits: Dict[str, Tuple[int, float]] = {}
_dynamic_lock: "asyncio.Lock | None" = None
_redis_client: Any = None
_redis_lock:   "asyncio.Lock | None" = None

_LUA_SLIDING_WINDOW = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count < limit then
    redis.call('ZADD', key, now, now .. math.random())
    redis.call('EXPIRE', key, window)
    return {1, limit - count - 1}
end
return {0, 0}
"""

_DEFAULT_RATE_LIMIT = 60
_DEFAULT_WINDOW_S   = 60


def _get_dynamic_lock() -> asyncio.Lock:
    """CRIT-A: lazy init — always called inside running event loop."""
    global _dynamic_lock
    if _dynamic_lock is None:
        _dynamic_lock = asyncio.Lock()
    return _dynamic_lock


def _get_redis_lock() -> asyncio.Lock:
    """CRIT-A: lazy init."""
    global _redis_lock
    if _redis_lock is None:
        _redis_lock = asyncio.Lock()
    return _redis_lock


def _get_redis() -> Any:
    return _redis_client


async def _check_redis_limit(key: str, window: int, limit: int) -> Tuple[bool, int]:
    r = _redis_client
    if r is None:
        return True, limit
    try:
        now_ms = int(time.monotonic() * 1000)
        result = await r.eval(_LUA_SLIDING_WINDOW, 1, key, now_ms, window * 1000, limit)
        return bool(result[0]), int(result[1])
    except Exception as exc:
        logger.warning("Redis rate-limit error: %s", exc)
        return True, limit


def reduce_rate_limit_for_ip(ip: str, new_limit: int, duration_s: float = 3600.0) -> None:
    _dynamic_ip_limits[ip] = (new_limit, time.monotonic() + duration_s)


def _get_limit_for_ip(ip: str) -> int:
    entry = _dynamic_ip_limits.get(ip)
    if entry is None:
        return _DEFAULT_RATE_LIMIT
    limit, expires = entry
    if time.monotonic() > expires:
        del _dynamic_ip_limits[ip]
        return _DEFAULT_RATE_LIMIT
    return limit


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter. Redis-backed when available."""

    def __init__(self, app: ASGIApp, default_limit: int = _DEFAULT_RATE_LIMIT,
                 window_s: int = _DEFAULT_WINDOW_S) -> None:
        super().__init__(app)
        self._default_limit = default_limit
        self._window        = window_s
        self._counters: Dict[str, deque] = {}

    def _get_client_ip(self, request: Request) -> str:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _check_in_memory(self, ip: str, limit: int) -> Tuple[bool, int]:
        now = time.monotonic()
        bucket = self._counters.setdefault(ip, deque())
        while bucket and (now - bucket[0]) > self._window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False, 0
        bucket.append(now)
        return True, limit - len(bucket)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        ip    = self._get_client_ip(request)
        limit = _get_limit_for_ip(ip)
        key   = f"rl:{ip}"
        if _redis_client is not None:
            allowed, remaining = await _check_redis_limit(key, self._window, limit)
        else:
            allowed, remaining = self._check_in_memory(ip, limit)
        if not allowed:
            return JSONResponse(
                {"error": "Rate limit exceeded", "retry_after": self._window},
                status_code=429,
                headers={"Retry-After": str(self._window), "X-RateLimit-Limit": str(limit)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"]     = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


async def start_cleanup_task(redis_url: Optional[str] = None) -> None:
    global _redis_client
    if redis_url:
        try:
            import aioredis  # type: ignore[import]
            _redis_client = await aioredis.from_url(redis_url, decode_responses=False)
            logger.info("Rate-limiter: Redis connected at %s", redis_url)
        except Exception as exc:
            logger.warning("Rate-limiter: Redis unavailable (%s); in-memory fallback", exc)


async def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None


# ── Phase S additions (S-13..S-16) ────────────────────────────────────────

_PRIVATE_PREFIXES = (
    "127.", "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
    "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
    "192.168.", "::1", "fc", "fd",
)


def extract_real_ip(
    remote_addr: str,
    forwarded_for: Optional[str],
    real_ip_header: Optional[str] = None,
    trust_proxy: bool = True,
) -> str:
    """S-14: Safe IP extraction — prevents X-Forwarded-For spoofing."""
    if real_ip_header and real_ip_header.strip():
        return real_ip_header.strip()
    if not trust_proxy or not forwarded_for:
        return remote_addr or "unknown"
    is_private = any((remote_addr or "").startswith(p) for p in _PRIVATE_PREFIXES)
    if not is_private:
        return remote_addr or "unknown"
    ips = [ip.strip() for ip in forwarded_for.split(",")]
    return ips[0] if ips else remote_addr or "unknown"


class WebSocketRateLimiter:
    """S-15: Per-IP WebSocket upgrade rate limiter."""

    def __init__(self, max_concurrent: int = 5, upgrade_window_s: int = 60,
                 max_upgrades: int = 10) -> None:
        self._max_concurrent = max_concurrent
        self._upgrade_window = upgrade_window_s
        self._max_upgrades   = max_upgrades
        self._active:        Dict[str, int]   = {}
        self._upgrade_times: Dict[str, deque] = {}
        self._lock = asyncio.Lock()

    async def can_connect(self, ip: str) -> Tuple[bool, str]:
        async with self._lock:
            if self._active.get(ip, 0) >= self._max_concurrent:
                return False, f"max_concurrent={self._max_concurrent} reached"
            now = time.monotonic()
            times = self._upgrade_times.setdefault(ip, deque())
            while times and (now - times[0]) > self._upgrade_window:
                times.popleft()
            if len(times) >= self._max_upgrades:
                return False, "upgrade_rate limit exceeded"
            times.append(now)
            self._active[ip] = self._active.get(ip, 0) + 1
            return True, "ok"

    async def on_disconnect(self, ip: str) -> None:
        async with self._lock:
            self._active[ip] = max(0, self._active.get(ip, 0) - 1)


class BurstAwareLimiter:
    """S-16: Sliding window with burst cap."""

    def __init__(self, max_requests: int, window_s: int,
                 burst_multiplier: float = 1.5) -> None:
        self._max_requests = max_requests
        self._window       = window_s
        self._burst_limit  = int(max_requests * burst_multiplier)
        self._timestamps:  deque = deque()

    def is_allowed(self) -> bool:
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) > self._window:
            self._timestamps.popleft()
        recent = sum(1 for t in self._timestamps if (now - t) <= 1.0)
        if recent >= self._burst_limit:
            return False
        if len(self._timestamps) >= self._max_requests:
            return False
        self._timestamps.append(now)
        return True

    def remaining(self) -> int:
        now = time.monotonic()
        while self._timestamps and (now - self._timestamps[0]) > self._window:
            self._timestamps.popleft()
        return max(0, self._max_requests - len(self._timestamps))


ws_rate_limiter = WebSocketRateLimiter()
