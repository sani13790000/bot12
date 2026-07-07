"""
backend/middleware/security_headers.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Starlette / FastAPI middleware that injects security-related HTTP
response headers on every outbound response.

Headers applied
---------------
- Strict-Transport-Security (HSTS)
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options
- X-XSS-Protection
- Referrer-Policy
- Permissions-Policy
- Cache-Control (for API responses)

Usage::

    from backend.middleware.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)
"""

from __future__ import annotations

from typing import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# ── Header values ────────────────────────────────────────────────────────── #

# HSTS: force HTTPS for one year, include sub-domains
_HSTS = "max-age=31536000; includeSubDomains; preload"

# CSP: strict policy suitable for a JSON API
# React dashboard assets are served from the same origin.
_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self';"
)

# Permissions-Policy: disable features not needed by the app
_PERMISSIONS = "camera=(), microphone=(), geolocation=(), interest-cohort=()"

# Cache-Control for API responses (prevents caching of sensitive data)
_CACHE_CONTROL = "no-store, no-cache, must-revalidate, private"

# Security headers to set on every response
_SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": _HSTS,
    "Content-Security-Policy": _CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "0",  # modern browsers ignore this; set to 0
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": _PERMISSIONS,
}


# ── Middleware class ───────────────────────────────────────────────────────── #


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Inject security headers into every HTTP response.

    Optionally applies ``Cache-Control: no-store`` to paths that start
    with ``/api/`` (configurable via *cache_api_responses*).
    """

    def __init__(self, app: object, cache_api_responses: bool = False) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._cache_api = cache_api_responses

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        # Prevent caching of API responses
        if not self._cache_api and request.url.path.startswith("/api"):
            response.headers["Cache-Control"] = _CACHE_CONTROL

        return response
