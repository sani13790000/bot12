"""backend/middleware/security_headers.py — stub"""
from __future__ import annotations
import logging
import secrets
from typing import Any, Callable, Awaitable
logger = logging.getLogger(__name__)

_blocked: set[str] = set()

def block_ip(ip: str) -> None:
    _blocked.add(ip)

def unblock_ip(ip: str) -> None:
    _blocked.discard(ip)

def blocked_ips() -> set[str]:
    return set(_blocked)

def _detect_injection(value: str) -> str | None:
    import re
    sql = re.compile(r"(?i)(select\s|insert\s|drop\s|delete\s|update\s|;\s*drop|union\s|1=1)")
    xss = re.compile(r"(?i)(<script|javascript:|onerror=|onload=)")
    if sql.search(value): return "sql"
    if xss.search(value): return "xss"
    return None

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response, JSONResponse

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        def __init__(self, app: Any, environment: str = "development",
                     allowed_origins: list[str] | None = None,
                     enable_csp_nonce: bool = False) -> None:
            super().__init__(app)
            self.environment = environment
            self.allowed_origins = allowed_origins or []
            self.enable_csp_nonce = enable_csp_nonce

        async def dispatch(self, request: Request,
                           call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            # Check blocked IPs
            client_ip = request.client.host if request.client else ""
            if client_ip in _blocked:
                return JSONResponse({"error": "forbidden"}, status_code=403)

            # Check injection in query params
            for v in request.query_params.values():
                if _detect_injection(v):
                    return JSONResponse({"error": "bad request"}, status_code=400)

            nonce = secrets.token_urlsafe(16) if self.enable_csp_nonce else ""
            if self.enable_csp_nonce:
                request.state.csp_nonce = nonce

            try:
                response = await call_next(request)
            except Exception:
                return JSONResponse({"error": "internal error"}, status_code=500)

            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["X-Request-ID"] = secrets.token_hex(8)
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

            if self.environment == "production":
                response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"

            return response
except ImportError:
    class SecurityHeadersMiddleware:  # type: ignore
        pass

__all__ = ["SecurityHeadersMiddleware", "_detect_injection", "block_ip", "unblock_ip", "blocked_ips"]
