"""
backend/middleware/security.py
Galaxy Vast AI Trading Platform -- Security Middleware
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

_RATE_LIMITS: dict[str, list[float]] = {}   # ip -> [timestamps]
RATE_WINDOW   = 60.0   # seconds
RATE_MAX_REQS = 100    # per window


class SecurityMiddleware(BaseHTTPMiddleware):
    """Combined security middleware: rate limiting + request validation."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # -- rate limiting --
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        hits = _RATE_LIMITS.setdefault(client_ip, [])
        hits[:] = [t for t in hits if now - t < RATE_WINDOW]
        if len(hits) >= RATE_MAX_REQS:
            logger.warning("Rate limit exceeded for %s", client_ip)
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
            )
        hits.append(now)

        # -- content-type validation for POST/PUT/PATCH --
        if request.method in ("POST", "PUT", "PATCH"):
            ct = request.headers.get("content-type", "")
            if ct and "application/json" not in ct and "multipart" not in ct:
                logger.warning("Unsupported content-type %s from %s", ct, client_ip)

        return await call_next(request)
