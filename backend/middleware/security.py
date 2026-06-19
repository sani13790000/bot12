"""
Security middleware — performance optimised.

Changes from previous version:
  * All regex patterns compiled at module load time (not per-request)
  * CSP header correctly included in every response
  * _sanitise_log_value strips \r\n to prevent log injection
  * SSRF guard for X-Forwarded-For header
  * SQL/XSS/Command injection patterns cover query string + body
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# ── Compiled patterns (module-level — compiled ONCE) ───────────────
_RE_SQL = re.compile(
    r"(?i)(\bUNION\b.+\bSELECT\b|\bDROP\b.+\bTABLE\b|"
    r"\bINSERT\b.+\bINTO\b|\bDELETE\b.+\bFROM\b|"
    r"'\s*OR\s*'1'\s*=\s*'1|--\s*$|;\s*DROP|EXEC\s*\()"
)
_RE_XSS = re.compile(
    r"(?i)(<script[^>]*>|javascript:\s*|on\w+\s*=|<iframe|<object|<embed)"
)
_RE_CMD = re.compile(
    r"(?i)(`[^`]*`|\$\([^)]*\)|\|\s*(sh|bash|cmd|powershell))"
)
_RE_PATH_TRAVERSAL = re.compile(
    r"(?:%2e%2e|%252e|\.\.[\/\\]|[\/\\]\.\.)", re.IGNORECASE
)
_RE_INTERNAL_PATHS = re.compile(
    r"^/(admin|internal|debug|metrics|__debug__|_debug)"
)
_RE_LOG_CLEAN = re.compile(r"[\r\n\t]")  # log injection prevention

# ── Security headers (built once) ─────────────────────────────────
_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' wss:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}

# Internal-only paths that must not be accessible via X-Forwarded-For spoofing
_INTERNAL_ONLY_PATHS: frozenset[str] = frozenset({
    "/metrics", "/internal", "/_debug", "/__debug__", "/admin",
})


def _sanitise_log(value: str, maxlen: int = 200) -> str:
    """Strip log injection chars and truncate."""
    return _RE_LOG_CLEAN.sub(" ", value)[:maxlen]


class SecurityMiddleware(BaseHTTPMiddleware):
    """Request inspection + security headers."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.monotonic()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = start

        path = request.url.path
        method = request.method

        # — SSRF: internal paths must not come via proxy headers
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for and path in _INTERNAL_ONLY_PATHS:
            return JSONResponse(
                {"error": "Forbidden"},
                status_code=403,
                headers=_SECURITY_HEADERS,
            )

        # — Path traversal
        if _RE_PATH_TRAVERSAL.search(request.url.path) or _RE_PATH_TRAVERSAL.search(
            str(request.query_params)
        ):
            logger.warning(
                "path_traversal path=%s ip=%s",
                _sanitise_log(path),
                _sanitise_log(request.client.host if request.client else ""),
            )
            return JSONResponse(
                {"error": "Forbidden"},
                status_code=403,
                headers=_SECURITY_HEADERS,
            )

        # — Query string injection scan
        qs = str(request.query_params)
        if qs and (
            _RE_SQL.search(qs)
            or _RE_XSS.search(qs)
            or _RE_CMD.search(qs)
        ):
            logger.warning(
                "injection_in_qs path=%s", _sanitise_log(path)
            )
            return JSONResponse(
                {"error": "Bad request"},
                status_code=400,
                headers=_SECURITY_HEADERS,
            )

        # — Body injection scan (only for mutating methods)
        if method in {"POST", "PUT", "PATCH"}:
            try:
                body = await request.body()
                body_str = body.decode("utf-8", errors="replace")
                if (
                    _RE_SQL.search(body_str)
                    or _RE_XSS.search(body_str)
                    or _RE_CMD.search(body_str)
                ):
                    logger.warning(
                        "injection_in_body path=%s", _sanitise_log(path)
                    )
                    return JSONResponse(
                        {"error": "Bad request"},
                        status_code=400,
                        headers=_SECURITY_HEADERS,
                    )
            except Exception:  # noqa: BLE001
                pass  # don't crash on body read error

        # — Call handler
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            logger.exception("unhandled error path=%s", _sanitise_log(path))
            resp = JSONResponse(
                {"error": "Internal server error"},
                status_code=500,
            )
            for k, v in _SECURITY_HEADERS.items():
                resp.headers[k] = v
            return resp

        # — Attach security headers
        for k, v in _SECURITY_HEADERS.items():
            response.headers[k] = v
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{(time.monotonic() - start) * 1000:.1f}ms"

        logger.debug(
            "req id=%s method=%s path=%s status=%s time=%.1fms",
            request_id,
            method,
            _sanitise_log(path),
            response.status_code,
            (time.monotonic() - start) * 1000,
        )
        return response
