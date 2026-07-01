"""
backend/middleware/security.py
Galaxy Vast AI Trading Platform — Security Middleware
"""
from __future__ import annotations
import logging
import time
from typing import Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)
__all__ = ["SecurityMiddleware"]


class SecurityMiddleware(BaseHTTPMiddleware):
    """Basic security middleware: rate-limit, logging, request ID."""

    def __init__(self, app, max_requests_per_minute: int = 100) -> None:
        super().__init__(app)
        self._max_rpm = max_requests_per_minute
        self._request_counts: dict = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        client_ip = request.client.host if request.client else "unknown"

        # Simple rate-limit
        now_minute = int(start / 60)
        key = f"{client_ip}:{now_minute}"
        count = self._request_counts.get(key, 0) + 1
        self._request_counts[key] = count

        # Clean old keys
        old_keys = [k for k in self._request_counts if not k.endswith(str(now_minute))]
        for k in old_keys:
            del self._request_counts[k]

        if count > self._max_rpm:
            from starlette.responses import JSONResponse
            return JSONResponse({"error": "rate_limit_exceeded"}, status_code=429)

        response = await call_next(request)
        duration_ms = (time.time() - start) * 1000
        logger.debug("%s %s %d %.1fms", request.method, request.url.path, response.status_code, duration_ms)
        return response
