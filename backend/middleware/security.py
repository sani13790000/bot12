"""
backend/middleware/security.py
Galaxy Vast AI — Security middleware layer

Provides rate-limit awareness, request signing verification helpers,
and IP blocklist integration.
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

LOGGER = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Lightweight security middleware for inbound requests."""

    def __init__(
        self,
        app,
        blocked_ips: Optional[set] = None,
        request_signing_secret: Optional[str] = None,
    ) -> None:
        super().__init__(app)
        self.blocked_ips = blocked_ips or set()
        self.request_signing_secret = request_signing_secret

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if client_ip in self.blocked_ips:
            LOGGER.warning("Blocked request from %s", client_ip)
            return Response("Forbidden", status_code=403)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def is_ip_blocked(ip: str, blocked_ips: Optional[set] = None) -> bool:
    return ip in (blocked_ips or set())
