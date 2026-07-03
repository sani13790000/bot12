"""
backend/middleware/security_headers.py
Galaxy Vast AI - Security Headers Middleware (Phase 11)

Adds security headers to every HTTP response:
    P11-SH-1: Content-Security-Policy
    P11-SH-2: X-Frame-Options DENY
    P11-SH-3: X-Content-Type-Options nosniff
    P11-SH-4: Referrer-Policy strict-origin-when-cross-origin
    P11-SH-5: Permissions-Policy
    P11-SH-6: HSTS max-age=63072000
"""
from __future__ import annotations
import os
from typing import Awaitable, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

HSTS_MAX_AGE = int(os.getenv("HSTS_MAX_AGE", "63072000"))
FRAME_OPTIONS = os.getenv("X_FRAME_OPTIONS", "DENY")
ALLOWED_ORIGINS = os.getenv("ALLOWED_CDN_ORIGINS", "https://cdn.jsdelivr.net https://fonts.googleapis.com")

_CSP = (
    f"default-src 'self'; "
    f"script-src 'self' {ALLOWED_ORIGINS}; "
    f"style-src 'self' {ALLOWED_ORIGINS} 'unsafe-inline'; "
    f"img-src 'self' data: blob:; "
    f"font-src 'self' {ALLOWED_ORIGINS}; "
    f"connect-src 'self'; "
    f"frame-src 'none'; "
    f"object-src 'none'; "
    f"base-uri 'self'; "
    f"form-action 'self';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._csp = _CSP

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = self._csp
        response.headers["X-Frame-Options"] = FRAME_OPTIONS
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = f"max-age={HSTS_MAX_AGE}; includeSubDomains; preload"
        response.headers.pop("Server", None)
        response.headers.pop("X-Powered-By", None)
        return response
