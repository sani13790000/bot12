"""
backend/middleware/security_headers.py
Galaxy Vast AI - Security Headers Middleware (Phase 11)

Adds CSP, HSTS, X-Frame-Options, X-Content-Type-Options,
X-XSS-Protection, Referrer-Policy, Permissions-Policy.
"""
from __future__ import annotations
import logging
from typing import Awaitable, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' wss: https:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that adds security headers to every response."""

    def __init__(self, app, *, csp: str = _CSP, csp_report_only: bool = False,
                 csp_report_uri: str = "", hsts_max_age: int = 31_536_000,
                 include_sub: bool = True, preload: bool = False) -> None:
        super().__init__(app)
        self._csp             = csp
        self._csp_report_only = csp_report_only
        self._csp_report_uri  = csp_report_uri
        self._hsts_max_age    = hsts_max_age
        self._include_sub     = include_sub
        self._preload         = preload

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        csp_val  = self._csp
        if self._csp_report_uri:
            csp_val += f" report-uri {self._csp_report_uri};"
        key = "Content-Security-Policy-Report-Only" if self._csp_report_only else "Content-Security-Policy"
        response.headers[key] = csp_val
        if request.url.scheme == "https":
            hsts = f"max-age={self._hsts_max_age}"
            if self._include_sub: hsts += "; includeSubDomains"
            if self._preload:     hsts += "; preload"
            response.headers["Strict-Transport-Security"] = hsts
        response.headers["X-Frame-Options"]        = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-XSS-Protection"]       = "1; mode=block"
        response.headers["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"]     = "geolocation=(), microphone=(), camera=()"
        response.headers.pop("X-Powered-By", None)
        response.headers.pop("Server", None)
        return response
