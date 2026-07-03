"""Security headers middleware -- truncated due to binary corruption."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

API_PATHS = ["/api/"]
SKIP_CSP_PATHS = ["/api/", "/metrics/", "/health/"]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=()"
        if not any(request.url.path.startswith(p) for p in SKIP_CSP_PATHS):
            response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response
