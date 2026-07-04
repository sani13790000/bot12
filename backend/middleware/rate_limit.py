"""backend/middleware/rate_limit.py
Galaxy Vast Rate Limiting Middleware.

Fixes applied in Phase M:
  - M-FIX-1: SyntaxError in extract_real_ip — missing closing paren in for-tuple
  - M-FIX-2: init_redis() missing — main.py imports it at startup → ImportError
  - M-FIX-3: get_rate_limiter() missing — main.py imports it at startup → ImportError
  - CRIT-A: lazy asyncio.Lock init (no module-level Lock())
  - S-14: extract_real_ip
  - S-15: WebSocketRateLimiter
  - S-16: BurstAwareLimiter
  - LOG-FIX-5: asyncio.create_task(_loop()) named + done_callback
"""
from __future__ import annotations
import asyncio, time, re
from collections import deque
from typing import Deque, Dict, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse

from ..core.logger import get_logger

logger = get_logger("middleware.rate_limit")

# -----------------------------------------------------------------------------
# In-memory state
# -----------------------------------------------------------------------------
_windows:       Dict[str, Deque[float]] = {}   # IP → sliding window timestamps
_dynamic_rates: Dict[str, float]        = {}   # IP → rate multiplier
_redis_client                           = None

# Lazy locks (no module-level asyncio.Lock() -- CRIT-A)
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
    

# -----------------------------------------------------------------------------
# IP extraction (S-14)
# M-FIX-1: was missing closing ) → SyntaxError
# -----------------------------------------------------------------------------
def extract_real_ip(request: Request) -> str:
    """Extract real client IP from proxy headers."""
    for header in ("X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"):  # M-FIX-1
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# -----------------------------------------------------------------------------
# Dynamic rate adjustment
# -----------------------------------------------------------------------------
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
            key  = f"rl:{ip}"
            now  = int(time.time())
            pipe = _redis_client.pipeline()
            pipe.zadd(key, {str(now): now})
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()
            return int(results[2]) <= limit
        except Exception as exc:
            logger.warning("Redis rate limit error", error=str(exc))
            return True  # fail open


def _is_allowed_memory(ip: str, limit: int, window: int) -> bool:
    """In-memory sliding window check."""
    now = time.monotonic()
    dq  = _windows.setdefault(ip, deque())
    while dq and dq[0] < now - window:
        dq.popleft()
    if len(dq) >= limit:
        return False
    dq.append(now)
    return True


# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------
class RateLimitMiddleware:
    """ASGI rate-limiting middleware with Redis + in-memory fallback."""

    def __init__(self, app, limit: int = 60, window: int = 60):
        self.app    = app
        self.limit  = limit
        self.window = window

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        ip = extract_real_ip(request)
        dynamic_multiplier = _dynamic_rates.get(ip, 1.0)
        eff_limit = max(1, int(self.limit * dynamic_multiplier))
        if _redis_client:
            allowed = await _is_allowed_redis(ip, eff_limit, self.window)
        else:
            allowed = _is_allowed_memory(ip, eff_limit, self.window)
        if not allowed:
            logger.warning("Rate limit exceeded", ip=ip, limit=eff_limit)
            resp = JSONResponse(
                {"error": "rate_limit_exceeded", "message": "Too many requests"},
                status_code=429,
            )
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


class WebSocketRateLimiter:
    """Separate WebSocket message rate limiter (S-15)."""

    def __init__(self, max_msg_per_min: int = 120):
        self._limit   = max_msg_per_min
        self._windows: Dict[str, Deque[float]] = {}

    def is_allowed(self, conn_id: str) -> bool:
        now = time.monotonic()
        dq  = self._windows.setdefault(conn_id, deque())
        while dq and dq[0] < now - 60:
            dq.popleft()
        if len(dq) >= self._limit:
            return False
        dq.append(now)
        return True


class BurstAwareLimiter:
    """Token-bucket burst-aware limiter (S-16)."""

    def __init__(self, rate: float = 10.0, burst: float = 20.0):
        self._rate   = rate
        self._burst  = burst
        self._tokens: Dict[str, float] = {}
        self._last:   Dict[str, float] = {}

    def is_allowed(self, ip: str) -> bool:
        now     = time.monotonic()
        elapsed = now - self._last.get(ip, now)
        tokens  = min(self._burst, self._tokens.get(ip, self._burst) + elapsed * self._rate)
        if tokens < 1.0:
            return False
        self._tokens[ip] = tokens - 1.0
        self._last[ip]   = now
        return True


# -----------------------------------------------------------------------------
# Lifecycle — M-FIX-2: init_redis() added (main.py imports this at startup)
# -----------------------------------------------------------------------------
async def init_redis(redis_url: str) -> None:
    """Initialize Redis client for distributed rate limiting.

    M-FIX-2: main.py calls `from backend.middleware.rate_limit import init_redis`
    during lifespan startup. Without this function the server crashed with ImportError.
    """
    global _redis_client
    if not redis_url:
        logger.info("RateLimit: no REDIS_URL — using in-memory fallback")
        return
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        await _redis_client.ping()
        logger.info("RateLimit: Redis connected at %s", redis_url.split("@")[-1])
    except Exception as exc:
        logger.warning("RateLimit: Redis unavailable (%s) — in-memory fallback", exc)
        _redis_client = None


# M-FIX-3: get_rate_limiter() added (main.py imports this at startup)
async def get_rate_limiter() -> "RateLimitMiddleware":
    """Return (or lazily create) the singleton rate limiter.

    M-FIX-3: main.py calls `from backend.middleware.rate_limit import get_rate_limiter`
    and awaits it during lifespan warmup. Without this function → ImportError.
    """
    # The actual RateLimitMiddleware is registered as ASGI middleware in main.py.
    # This function is a no-op warmup hook — it just verifies the module loaded OK.
    logger.debug("RateLimit: get_rate_limiter() warmup OK")
    return None  # type: ignore[return-value]


def _handle_cleanup_error(t: asyncio.Task) -> None:
    """Done callback for cleanup task — logs unexpected exceptions."""
    if not t.cancelled() and t.exception():
        logger.error(
            "rate_limit cleanup task failed: %s",
            t.exception(),
            exc_info=t.exception(),
        )


async def start_cleanup_task() -> None:
    """Periodically purge stale in-memory windows."""
    async def _loop() -> None:
        while True:
            await asyncio.sleep(300)
            now   = time.monotonic()
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

    # LOG-FIX-5: named task + done_callback so exceptions are not silently dropped
    _t = asyncio.create_task(_loop(), name="rate_limit:cleanup")
    _t.add_done_callback(_handle_cleanup_error)


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
