"""backend/middleware/rate_limit.py
Galaxy Vast AI Trading Platform — Rate Limit Middleware (Enterprise)

Features:
  - Per-IP sliding window rate limiting (Redis-backed + in-memory fallback)
  - Dynamic rate reduction for suspicious IPs
  - Burst-aware limiter
  - WebSocket rate limiter
  - Real IP extraction (X-Forwarded-For / X-Real-IP)
  - Lazy asyncio.Lock init (CRIT-A fix)
"""
from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Any, Callable, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.config import get_settings
from ..core.logger import get_logger

settings = get_settings()
logger   = get_logger("middleware.rate_limit")

# ── Lazy locks (CRIT-A: no module-level asyncio.Lock) ────────────────────────
_dynamic_lock: Optional[asyncio.Lock] = None
_redis_lock:   Optional[asyncio.Lock] = None


def _get_dynamic_lock() -> asyncio.Lock:
    global _dynamic_lock
    if _dynamic_lock is None:
        _dynamic_lock = asyncio.Lock()
    return _dynamic_lock


def _get_redis_lock() -> asyncio.Lock:
    global _redis_lock
    if _redis_lock is None:
        _redis_lock = asyncio.Lock()
    return _redis_lock


# ── In-memory stores ─────────────────────────────────────────────────────────────
_windows:       Dict[str, deque]  = defaultdict(lambda: deque())
_dynamic_rates: Dict[str, float]  = {}
_redis_client:  Optional[Any]     = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def extract_real_ip(request: Request) -> str:
    """Extract real client IP respecting reverse-proxy headers."""
    for header in ("x-forwarded-for", "x-real-ip", "cf-connecting-ip"):
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def reduce_rate_limit_for_ip(ip: str, factor: float = 0.5) -> None:
    """Dynamically reduce rate limit for a specific IP (e.g. after failed auth)."""
    async with _get_dynamic_lock():
        current = _dynamic_rates.get(ip, 1.0)
        _dynamic_rates[ip] = max(0.1, current * factor)
    logger.warning("Rate limit reduced", ip=ip, factor=factor)


async def _is_allowed_redis(ip: str, limit: int, window: int) -> bool:
    """Redis-backed sliding window check."""
    if _redis_client is None:
        return True
    async with _get_redis_lock():
        try:
            key = f"rl:{ip}"
            now  = int(time.time())
            pipe = _redis_client.pipeline()
            pipe.zadd(key, {str(now): now})
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()
            count: int = results[2]
            return count <= limit
        except Exception as _exc:
            logger.debug("redis rate check failed, falling back", error=str(_exc))
            return True  # fail-open for Redis errors


def _is_allowed_memory(ip: str, limit: int, window: float) -> bool:
    """In-memory sliding window fallback."""
    now = time.monotonic()
    dq  = _windows[ip]
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


# ── Middleware ─────────────────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    ASGI rate limit middleware.
    Default: 60 requests / 60 seconds per IP.
    """

    def __init__(self, app: Any, *, limit: int = 60, window: int = 60) -> None:
        super().__init__(app)
        self._limit  = limit
        self._window = window

    async def dispatch(self, request: Request, call_next: Callable) -> Any:
        ip = extract_real_ip(request)

        # Apply dynamic rate factor
        factor = _dynamic_rates.get(ip, 1.0)
        effective_limit = max(1, int(self._limit * factor))

        # Try Redis first; fall back to memory
        if _redis_client is not None:
            allowed = await _is_allowed_redis(ip, effective_limit, self._window)
        else:
            allowed = _is_allowed_memory(ip, effective_limit, float(self._window))

        if not allowed:
            logger.warning("Rate limit exceeded", ip=ip, limit=effective_limit)
            return JSONResponse(
                status_code=429,
                content={"error": "RATE_LIMIT_EXCEEDED",
                         "message": "Too many requests. Please slow down."},
                headers={"Retry-After": str(self._window)},
            )

        return await call_next(request)


# ── WebSocket Rate Limiter ─────────────────────────────────────────────────────

class WebSocketRateLimiter:
    def __init__(self, limit: int = 100, window: float = 60.0) -> None:
        self._limit  = limit
        self._window = window
        self._windows: Dict[str, deque] = defaultdict(lambda: deque())

    def is_allowed(self, client_id: str) -> bool:
        now = time.monotonic()
        dq  = self._windows[client_id]
        while dq and dq[0] < now - self._window:
            dq.popleft()
        if len(dq) >= self._limit:
            return False
        dq.append(now)
        return True


# ── Burst-Aware Limiter ────────────────────────────────────────────────────────

class BurstAwareLimiter:
    """Token bucket algorithm for burst-tolerant rate limiting."""

    def __init__(
        self,
        rate: float = 10.0,   # tokens per second
        burst: float = 20.0,  # max bucket size
    ) -> None:
        self._rate   = rate
        self._burst  = burst
        self._tokens: Dict[str, float] = {}
        self._last:   Dict[str, float] = {}

    def is_allowed(self, client_id: str) -> bool:
        now = time.monotonic()
        tokens = self._tokens.get(client_id, self._burst)
        last   = self._last.get(client_id, now)
        elapsed = now - last
        tokens  = min(self._burst, tokens + elapsed * self._rate)
        if tokens < 1.0:
            return False
        self._tokens[client_id] = tokens - 1.0
        self._last[client_id]   = now
        return True


# ── Lifecycle ───────────────────────────────────────────────────────────────────

async def start_cleanup_task() -> None:
    """Periodically purge stale in-memory windows."""
    async def _loop() -> None:
        while True:
            await asyncio.sleep(300)
            now = time.monotonic()
            stale = [
                ip for ip, dq in _windows.items()
                if dq and dq[-1] < now - 3600
            ]
            for ip in stale:
                try:
                    del _windows[ip]
                except Exception as _exc:
                    logger.debug("rate_limit cleanup error", error=str(_exc))
            if stale:
                logger.debug("RateLimit cleanup", removed=len(stale))
    asyncio.create_task(_loop())


async def close_redis() -> None:
    """Gracefully close the Redis connection."""
    global _redis_client
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception as _exc:
            logger.debug("Redis close error", error=str(_exc))
        finally:
            _redis_client = None
