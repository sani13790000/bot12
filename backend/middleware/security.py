"""Security Middleware — Galaxy Vast AI Trading Platform

Fixes applied:
  - Content-Security-Policy header added
  - SQL injection check extended to query string (not just body)
  - Log injection prevention (path sanitized before logging)
"""
from __future__ import annotations

import re
import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from backend.core.logger import get_logger

logger = get_logger("middleware.security")

# SQL injection patterns — checked in BOTH body AND query string
_SQL_PATTERNS = re.compile(
    r"(\bunion\b|\bselect\b|\binsert\b|\bupdate\b|\bdelete\b|\bdrop\b"
    r"|\btruncate\b|\bexec\b|\bexecute\b|--|;\s*--|xp_|0x[0-9a-f]+"
    r"|\bcast\s*\(|\bconvert\s*\(|\bchar\s*\(|\bnchar\s*\()",
    re.IGNORECASE,
)

# XSS patterns
_XSS_PATTERNS = re.compile(
    r"(<script|javascript:|vbscript:|onload=|onerror=|onclick=|<iframe|<object|<embed)",
    re.IGNORECASE,
)

# Safe path sanitizer for logging (strip newlines)
_NEWLINE_RE = re.compile(r"[\r\n]")


class SecurityMiddleware(BaseHTTPMiddleware):
    """Production security middleware."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start = time.monotonic()

        # Attach request_id for downstream use
        request.state.request_id = request_id

        # ── 1. SQL Injection check — query string ──
        query_string = request.url.query
        if query_string and _SQL_PATTERNS.search(query_string):
            logger.warning(
                "SQL injection attempt in query string | id=%s ip=%s path=%s",
                request_id,
                request.client.host if request.client else "unknown",
                _NEWLINE_RE.sub("", str(request.url.path)),
            )
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=400, content={"detail": "Invalid request"})

        # ── 2. SQL Injection + XSS check — body ──
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                body_text = body_bytes.decode("utf-8", errors="replace")

                if _SQL_PATTERNS.search(body_text):
                    logger.warning(
                        "SQL injection attempt in body | id=%s ip=%s",
                        request_id,
                        request.client.host if request.client else "unknown",
                    )
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=400, content={"detail": "Invalid request"})

                if _XSS_PATTERNS.search(body_text):
                    logger.warning(
                        "XSS attempt in body | id=%s ip=%s",
                        request_id,
                        request.client.host if request.client else "unknown",
                    )
                    from fastapi.responses import JSONResponse
                    return JSONResponse(status_code=400, content={"detail": "Invalid request"})
            except Exception:  # noqa: BLE001
                pass  # don't block on body read failure

        # ── 3. Process request ──
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        # ── 4. Security headers ──
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP — was missing, now added
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' wss:; "
            "frame-ancestors 'none'"
        )

        # ── 5. Audit log (sanitized) ──
        safe_path = _NEWLINE_RE.sub("", str(request.url.path))
        user_id = getattr(request.state, "user_id", None)
        logger.info(
            "REQ id=%s method=%s path=%s status=%s duration_ms=%s ip=%s user=%s",
            request_id,
            request.method,
            safe_path,
            response.status_code,
            duration_ms,
            request.client.host if request.client else "unknown",
            user_id,
        )

        return response
