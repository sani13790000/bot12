"""
backend/middleware/security.py
Security middleware — injected before every request.

Protections:
- SQL Injection (body + query string)
- XSS (body)
- Command Injection (body)
- Path Traversal (URL)
- Request size limit
- Security response headers (CSP, HSTS, X-Frame, etc.)
- Log injection sanitisation
- SSRF guard on internal admin endpoints
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Awaitable, Callable, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_BODY_BYTES = 1 * 1024 * 1024  # 1 MB

# SQL Injection patterns (body + query)
_SQL_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"('\s*(or|and)\s*'?\d)",
        r"(--|#|/\*)[^\n]*",
        r"\b(union\s+select|drop\s+table|truncate\s+table|exec\s*\(|xp_cmdshell)\b",
        r";\s*(drop|delete|insert|update|create|alter|replace)\s",
        r"(sleep\s*\(|benchmark\s*\(|waitfor\s+delay)",
    ]
]

# Command Injection
_CMD_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"[;&|`$]\s*(rm|wget|curl|bash|sh|python|perl|nc|cat|ls)\b",
        r"\$\(.*\)",
        r"`[^`]+`",
    ]
]

# XSS
_XSS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"<script[^>]*>.*?</script>",
        r"javascript\s*:",
        r"on(load|click|error|mouseover|focus|blur)\s*=",
        r"<iframe[^>]*>",
        r"expression\s*\(",
    ]
]

# Path Traversal
_PATH_TRAVERSAL = re.compile(r"(\.\./|\.\.\\|%2e%2e|%252e%252e)", re.IGNORECASE)

# Safe log pattern
_UNSAFE_LOG_CHARS = re.compile(r"[\r\n\t]")  # newline injection

# Endpoints that should NEVER be reachable from external requests
# (SSRF guard — block if X-Forwarded-For is set and path matches)
_INTERNAL_ONLY_PATHS: Set[str] = {
    "/internal/",
    "/admin/metrics",
    "/admin/debug",
}

# CSP value
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' wss:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Security response headers
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": _CSP,
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_log(value: str, max_len: int = 200) -> str:
    """Remove log-injection characters and truncate."""
    return _UNSAFE_LOG_CHARS.sub(" ", value)[:max_len]


def _check_patterns(text: str, patterns: list[re.Pattern]) -> bool:
    """Return True if any pattern matches *text*."""
    return any(p.search(text) for p in patterns)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

class SecurityMiddleware(BaseHTTPMiddleware):
    """Request-level security checks + security response headers."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        # -- 0. Attach request id --
        request.state.request_id = request_id

        # -- 1. Path traversal in URL --
        raw_path = request.url.path
        if _PATH_TRAVERSAL.search(raw_path):
            log.warning("[%s] Path traversal attempt: %s", request_id, _sanitise_log(raw_path))
            return JSONResponse(
                {"detail": "Bad request"},
                status_code=400,
                headers={"X-Request-ID": request_id},
            )

        # -- 2. SSRF guard: internal paths from external requests --
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            for internal in _INTERNAL_ONLY_PATHS:
                if raw_path.startswith(internal):
                    log.warning(
                        "[%s] SSRF attempt on internal path: %s from %s",
                        request_id, _sanitise_log(raw_path), _sanitise_log(forwarded_for),
                    )
                    return JSONResponse(
                        {"detail": "Not found"},
                        status_code=404,
                        headers={"X-Request-ID": request_id},
                    )

        # -- 3. Query string checks --
        qs = str(request.url.query)
        if qs:
            if _check_patterns(qs, _SQL_PATTERNS):
                log.warning("[%s] SQL injection in query string", request_id)
                return JSONResponse({"detail": "Bad request"}, status_code=400)

        # -- 4. Body checks (only for mutating methods) --
        if request.method in ("POST", "PUT", "PATCH"):
            body_bytes = await request.body()

            # Size limit
            if len(body_bytes) > _MAX_BODY_BYTES:
                log.warning("[%s] Request body too large: %d bytes", request_id, len(body_bytes))
                return JSONResponse({"detail": "Request body too large"}, status_code=413)

            body_text = body_bytes.decode("utf-8", errors="replace")

            if _check_patterns(body_text, _SQL_PATTERNS):
                log.warning("[%s] SQL injection pattern in body", request_id)
                return JSONResponse({"detail": "Bad request"}, status_code=400)

            if _check_patterns(body_text, _CMD_PATTERNS):
                log.warning("[%s] Command injection pattern in body", request_id)
                return JSONResponse({"detail": "Bad request"}, status_code=400)

            if _check_patterns(body_text, _XSS_PATTERNS):
                log.warning("[%s] XSS pattern in body", request_id)
                return JSONResponse({"detail": "Bad request"}, status_code=400)

        # -- 5. Process request --
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            log.error("[%s] Unhandled exception: %s", request_id, type(exc).__name__)
            return JSONResponse(
                {"detail": "Internal server error"},
                status_code=500,
                headers={"X-Request-ID": request_id},
            )

        # -- 6. Inject security headers --
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        response.headers["X-Request-ID"] = request_id

        # -- 7. Audit log --
        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "[%s] %s %s → %d (%dms)",
            request_id,
            request.method,
            _sanitise_log(raw_path),
            response.status_code,
            duration_ms,
        )

        return response
