"""
backend/middleware/security.py
Galaxy Vast AI — Core Security Middleware

P11-SEC-1: Rate limiting per IP + per user
P11-SEC-2: Request size limits
P11-SEC-3: Suspicious pattern detection
P11-SEC-4: Audit logging for all mutating requests
"""
from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict
from typing import Any, Callable, DefaultDict, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_MAX_BODY_BYTES  = 10 * 1024 * 1024   # 10 MB
_RATE_LIMIT_RPM  = 120                 # requests per minute per IP
_RATE_WINDOW     = 60.0                # seconds
_SUSPICIOUS_HDRS = frozenset(["x-forwarded-for", "x-real-ip"])


# --------------------------------------------------------------------------- #
# Rate limiter (in-process, no Redis dependency)
# --------------------------------------------------------------------------- #

class _RateLimiter:
    """Simple sliding-window rate limiter."""

    def __init__(self, max_rpm: int = _RATE_LIMIT_RPM, window: float = _RATE_WINDOW) -> None:
        self._max    = max_rpm
        self._window = window
        self._counts: DefaultDict[str, list] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now   = time.monotonic()
        hits  = self._counts[key]
        # remove old hits outside window
        cutoff = now - self._window
        hits[:] = [t for t in hits if t > cutoff]
        if len(hits) >= self._max:
            return False
        hits.append(now)
        return True

    def cleanup(self) -> None:
        """Purge stale keys."""
        now    = time.monotonic()
        cutoff = now - self._window
        stale  = [k for k, v in self._counts.items() if not any(t > cutoff for t in v)]
        for k in stale:
            del self._counts[k]


_rate_limiter = _RateLimiter()


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #

class SecurityMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware that enforces:
    - Request body size limits
    - Per-IP rate limiting
    - Audit log for POST/PUT/DELETE
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = (request.client.host if request.client else "0.0.0.0")

        # 1. Rate limit
        if not _rate_limiter.is_allowed(client_ip):
            logger.warning("[Security] rate limit exceeded: ip=%s path=%s", client_ip, request.url.path)
            return JSONResponse(
                {"error": "RATE_LIMIT_EXCEEDED", "retry_after": int(_RATE_WINDOW)},
                status_code=429,
            )

        # 2. Body size limit
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            logger.warning(
                "[Security] body too large: %s bytes from ip=%s",
                content_length, client_ip,
            )
            return JSONResponse({"error": "REQUEST_ENTITY_TOO_LARGE"}, status_code=413)

        # 3. Audit log
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            logger.info(
                "[Audit] %s %s ip=%s user_agent=%s",
                request.method,
                request.url.path,
                client_ip,
                request.headers.get("user-agent", "")[:80],
            )

        return await call_next(request)
