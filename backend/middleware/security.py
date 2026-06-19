"""Security middleware — request hardening, audit logging, threat detection.

Fixes applied:
- Added Content-Security-Policy header (was missing, XSS risk)
- SQL injection scan now covers BOTH body AND query string
- Log injection prevention: path sanitised before logging
- Improved security headers set
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import Callable, Sequence

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Threat-detection patterns
# ---------------------------------------------------------------------------

_SQLI_PATTERNS: Sequence[re.Pattern] = [
    re.compile(r"('\s*(or|and)\s*'?\d)|(-{2})|(/\*.*\*/)", re.I),
    re.compile(r"\b(union\s+select|drop\s+table|insert\s+into|delete\s+from|update\s+set)", re.I),
    re.compile(r"\b(sleep\s*\(|benchmark\s*\(|load_file\s*\(|into\s+outfile)", re.I),
    re.compile(r"(;\s*(drop|alter|create|truncate))", re.I),
]

_XSS_PATTERNS: Sequence[re.Pattern] = [
    re.compile(r"<\s*script[^>]*>", re.I),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"on(load|error|click|mouseover|focus)\s*=", re.I),
    re.compile(r"<\s*(iframe|object|embed|applet)[^>]*>", re.I),
]

# Paths that are exempt from threat scanning (e.g. health checks)
_SCAN_EXEMPT_PATHS: frozenset[str] = frozenset(["/health", "/", "/docs", "/openapi.json"])


def _sanitise_log_value(value: str, max_len: int = 200) -> str:
    """Strip newlines to prevent log-injection; truncate for readability."""
    return value.replace("\n", " ").replace("\r", " ")[:max_len]


def _scan_sql_injection(text: str) -> bool:
    for pat in _SQLI_PATTERNS:
        if pat.search(text):
            return True
    return False


def _scan_xss(text: str) -> bool:
    for pat in _XSS_PATTERNS:
        if pat.search(text):
            return True
    return False


class SecurityMiddleware(BaseHTTPMiddleware):
    """Production security middleware.

    - Assigns a unique request_id to every request
    - Scans body AND query string for SQLi / XSS patterns
    - Adds comprehensive security headers (including CSP)
    - Writes a structured audit log entry for every request
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        t_start = time.monotonic()

        path = request.url.path
        method = request.method

        # ----------------------------------------------------------------
        # Threat scanning (skip exempt paths)
        # ----------------------------------------------------------------
        if path not in _SCAN_EXEMPT_PATHS:
            # 1. Scan query string
            query_str = str(request.url.query)
            if _scan_sql_injection(query_str):
                logger.warning(
                    "SQLi pattern in query string | rid=%s path=%s",
                    request_id, _sanitise_log_value(path),
                )
                return Response(
                    content='{"detail":"Bad request"}',
                    status_code=400,
                    media_type="application/json",
                )

            # 2. Scan request body (only for mutating methods)
            if method in ("POST", "PUT", "PATCH"):
                try:
                    body_bytes = await request.body()
                    body_text = body_bytes.decode("utf-8", errors="replace")
                except Exception:  # noqa: BLE001
                    body_text = ""

                if _scan_sql_injection(body_text) or _scan_xss(body_text):
                    logger.warning(
                        "Threat pattern in body | rid=%s path=%s method=%s",
                        request_id, _sanitise_log_value(path), method,
                    )
                    return Response(
                        content='{"detail":"Bad request"}',
                        status_code=400,
                        media_type="application/json",
                    )

        # ----------------------------------------------------------------
        # Process request
        # ----------------------------------------------------------------
        response = await call_next(request)
        duration_ms = round((time.monotonic() - t_start) * 1000, 2)

        # ----------------------------------------------------------------
        # Security headers
        # ----------------------------------------------------------------
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        # Content-Security-Policy — was missing before this fix
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        )
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cache-Control"] = "no-store"

        # ----------------------------------------------------------------
        # Audit log
        # ----------------------------------------------------------------
        user_id = getattr(getattr(request.state, "user", None), "id", "anonymous")
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            "AUDIT rid=%s method=%s path=%s status=%d dur_ms=%s ip=%s uid=%s",
            request_id,
            method,
            _sanitise_log_value(path),  # sanitised — no log injection
            response.status_code,
            duration_ms,
            client_ip,
            user_id,
        )

        return response
