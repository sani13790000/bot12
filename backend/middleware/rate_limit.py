"""Rate Limit Middleware — Galaxy Vast AI Trading Platform

Fixes applied:
  - InMemoryRateLimiter._windows now has MAX_TRACKED_IPS=50_000 to prevent OOM under DDoS
  - Cleanup evicts oldest entries when limit exceeded
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.core.logger import get_logger

logger = get_logger("middleware.rate_limit")

# Per-path rate limit rules: (max_requests, window_seconds)
_RULES: Dict[str, Tuple[int, int]] = {
    "/api/v1/auth/login":    (5,  60),   # 5 per minute — brute-force protection
    "/api/v1/auth/register": (3,  60),   # 3 per minute
    "/api/v1/auth/refresh":  (10, 60),
    "/api/v1/backtest":      (10, 60),
    "/api/v1/backtest-engine": (5, 60),
    "/api/v1/institutional": (20, 60),
}
_DEFAULT_RULE: Tuple[int, int] = (100, 60)  # 100 per minute default

MAX_TRACKED_IPS = 50_000  # prevent OOM under DDoS


class InMemoryRateLimiter:
    """Sliding-window rate limiter — in-memory fallback."""

    def __init__(self) -> None:
        # {key: deque of timestamps}
        self._windows: Dict[str, Deque[float]] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def start_cleanup(self) -> None:
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(300)  # every 5 minutes
            now = time.time()
            expired = [
                k for k, dq in self._windows.items()
                if not dq or now - dq[-1] > 3600  # idle > 1h
            ]
            for k in expired:
                del self._windows[k]
            logger.debug("Rate limiter cleanup: removed %d idle keys", len(expired))

    def _evict_oldest(self) -> None:
        """Evict oldest 10% entries when MAX_TRACKED_IPS exceeded."""
        if len(self._windows) < MAX_TRACKED_IPS:
            return
        # Sort by last-seen timestamp (oldest first)
        sorted_keys = sorted(
            self._windows.keys(),
            key=lambda k: self._windows[k][-1] if self._windows[k] else 0
        )
        to_remove = max(1, MAX_TRACKED_IPS // 10)
        for k in sorted_keys[:to_remove]:
            del self._windows[k]
        logger.warning("Rate limiter: evicted %d oldest entries (DDoS protection)", to_remove)

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        now = time.time()
        cutoff = now - window_seconds

        if key not in self._windows:
            self._evict_oldest()
            self._windows[key] = deque()

        dq = self._windows[key]
        # Evict old timestamps
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= max_requests:
            return False
        dq.append(now)
        return True

    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        dq = self._windows.get(key, deque())
        now = time.time()
        cutoff = now - window_seconds
        active = sum(1 for t in dq if t >= cutoff)
        return max(0, max_requests - active)


class RedisRateLimiter:
    """Redis sliding-window rate limiter."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._client = None

    async def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = await aioredis.from_url(self._url, decode_responses=True)
            except Exception as exc:
                logger.warning("Redis rate limiter unavailable: %s", exc)
                return None
        return self._client

    async def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        client = await self._get_client()
        if client is None:
            return True  # fail open if Redis down
        now = time.time()
        cutoff = now - window_seconds
        pipe = client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window_seconds + 1)
        results = await pipe.execute()
        count = results[1]
        return count < max_requests


# ── Global limiter (in-memory primary, Redis optional) ──
_limiter = InMemoryRateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with per-path rules."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        # Start cleanup task in background
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_limiter._cleanup_loop())
        except RuntimeError:
            pass

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for health check
        if path in ("/health", "/", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        # Find applicable rule
        max_req, window = _DEFAULT_RULE
        for rule_path, rule in _RULES.items():
            if path.startswith(rule_path):
                max_req, window = rule
                break

        key = f"rl:{client_ip}:{path}"
        allowed = _limiter.is_allowed(key, max_req, window)
        remaining = _limiter.get_remaining(key, max_req, window)

        if not allowed:
            logger.warning("Rate limit exceeded | ip=%s path=%s", client_ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={
                    "X-RateLimit-Limit": str(max_req),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Window": str(window),
                    "Retry-After": str(window),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_req)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(window)
        return response
