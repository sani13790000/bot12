"""Rate Limit Middleware — Galaxy Vast AI
Fix: _windows dict capped at MAX_TRACKED_IPS to prevent OOM under DDoS
"""
from __future__ import annotations
import asyncio, time
from collections import deque
from typing import Callable, Deque, Dict, Optional, Tuple
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from backend.core.logger import get_logger

logger = get_logger("middleware.rate_limit")

_RULES: Dict[str, Tuple[int, int]] = {
    "/api/v1/auth/login":      (5,  60),
    "/api/v1/auth/register":   (3,  60),
    "/api/v1/auth/refresh":    (10, 60),
    "/api/v1/backtest":        (10, 60),
    "/api/v1/backtest-engine": (5,  60),
    "/api/v1/institutional":   (20, 60),
}
_DEFAULT: Tuple[int, int] = (100, 60)
MAX_TRACKED_IPS = 50_000
_SKIP = {"/health", "/", "/docs", "/openapi.json", "/redoc"}


class _Limiter:
    def __init__(self) -> None:
        self._w: Dict[str, Deque[float]] = {}

    def _evict(self) -> None:
        if len(self._w) < MAX_TRACKED_IPS:
            return
        n = max(1, MAX_TRACKED_IPS // 10)
        keys = sorted(self._w, key=lambda k: self._w[k][-1] if self._w[k] else 0)
        for k in keys[:n]:
            del self._w[k]
        logger.warning("Rate limiter evicted %d entries (DDoS protection)", n)

    def allow(self, key: str, max_r: int, win: int) -> Tuple[bool, int]:
        now, cutoff = time.time(), time.time() - win
        if key not in self._w:
            self._evict()
            self._w[key] = deque()
        dq = self._w[key]
        while dq and dq[0] < cutoff:
            dq.popleft()
        remaining = max(0, max_r - len(dq))
        if len(dq) >= max_r:
            return False, 0
        dq.append(now)
        return True, max(0, remaining - 1)


_lim = _Limiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if path in _SKIP:
            return await call_next(request)
        ip = request.client.host if request.client else "unknown"
        max_r, win = _DEFAULT
        for rp, rule in _RULES.items():
            if path.startswith(rp):
                max_r, win = rule
                break
        ok, remaining = _lim.allow(f"rl:{ip}:{path}", max_r, win)
        if not ok:
            logger.warning("Rate limit exceeded ip=%s path=%s", ip, path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests."},
                headers={"X-RateLimit-Limit": str(max_r), "X-RateLimit-Remaining": "0", "Retry-After": str(win)},
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_r)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
