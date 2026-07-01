"""
backend/middleware/security.py
Galaxy Vast AI - Security Middleware (repaired)
"""
from __future__ import annotations
import logging
import time
from collections import defaultdict
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)
_blocked_ips: set[str] = set()
_rate_windows: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW_S = 60.0

class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, rate_limit: int = RATE_LIMIT_REQUESTS) -> None:
        super().__init__(app)
        self._rate_limit = rate_limit

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if client_ip in _blocked_ips:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)
        now = time.time()
        window = _rate_windows[client_ip]
        window[:] = [t for t in window if now - t < RATE_LIMIT_WINDOW_S]
        if len(window) >= self._rate_limit:
            return JSONResponse({"detail": "Too Many Requests"}, status_code=429)
        window.append(now)
        return await call_next(request)

def block_ip(ip: str) -> None:
    _blocked_ips.add(ip)

def unblock_ip(ip: str) -> None:
    _blocked_ips.discard(ip)

def blocked_ips() -> set[str]:
    return set(_blocked_ips)

__all__ = ["SecurityMiddleware", "block_ip", "unblock_ip", "blocked_ips"]
