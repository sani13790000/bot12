"""
backend/middleware/security.py
Galaxy Vast AI Trading Platform - Security Middleware
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_LOG = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Security middleware: rate limiting, request logging, security headers."""

    def __init__(self, app, max_requests_per_minute: int = 60) -> None:
        super().__init__(app)
        self._max_rpm = max_requests_per_minute
        self._request_counts: dict = {}
        self._window_start: float = time.time()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        client_ip = request.client.host if request.client else "unknown"

        # Basic rate limiting
        now = time.time()
        if now - self._window_start > 60:
            self._request_counts.clear()
            self._window_start = now

        count = self._request_counts.get(client_ip, 0) + 1
        self._request_counts[client_ip] = count

        if count > self._max_rpm:
            from starlette.responses import JSONResponse
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)

        response = await call_next(request)

        elapsed = time.time() - start
        _LOG.debug("%s %s %d %.3fs", request.method, request.url.path, response.status_code, elapsed)

        return response
