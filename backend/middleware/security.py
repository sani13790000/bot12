"""
Phase 10 — Security Middleware
Input Validation + SQL Injection Prevention + XSS + Path Traversal + Audit Logging
"""
from __future__ import annotations

import re
import time
import uuid
import json
import hashlib
from typing import Optional, Set
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.observability import get_logger

logger = get_logger("security.middleware")

# ── SQL Injection patterns ──────────────────────────────────────────────────
_SQL_PATTERNS: list[re.Pattern] = [
    re.compile(r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|TRUNCATE)\b)", re.I),
    re.compile(r"(-{2}|/\*|\*/|;\s*$)"),
    re.compile(r"(\bOR\b\s+\d+=\d+|\bAND\b\s+\d+=\d+)", re.I),
    re.compile(r"(xp_|sp_|0x[0-9a-fA-F]+)", re.I),
    re.compile(r"('\s*(OR|AND)\s*'\d+'\s*=\s*'\d+')", re.I),
]

# ── XSS patterns ───────────────────────────────────────────────────────────
_XSS_PATTERNS: list[re.Pattern] = [
    re.compile(r"<script[^>]*>.*?</script>", re.I | re.S),
    re.compile(r"javascript\s*:", re.I),
    re.compile(r"on(load|click|error|mouseover|submit)\s*=", re.I),
    re.compile(r"<iframe[^>]*>", re.I),
    re.compile(r"eval\s*\(", re.I),
]

# ── Path traversal ─────────────────────────────────────────────────────────
_PATH_TRAVERSAL = re.compile(r"(\.\./|\.\.\\\\|%2e%2e|%252e)", re.I)

# ── Safe endpoints (skip body validation) ──────────────────────────────────
_SKIP_VALIDATION: Set[str] = {
    "/docs", "/redoc", "/openapi.json",
    "/health", "/observability/metrics",
}

# ── Max body size (1 MB) ────────────────────────────────────────────────────
_MAX_BODY_BYTES = 1 * 1024 * 1024


def _check_sql(value: str) -> bool:
    """True if SQL injection pattern detected."""
    for pat in _SQL_PATTERNS:
        if pat.search(value):
            return True
    return False


def _check_xss(value: str) -> bool:
    """True if XSS pattern detected."""
    for pat in _XSS_PATTERNS:
        if pat.search(value):
            return True
    return False


def _scan_value(val) -> Optional[str]:
    """Recursively scan a value; return threat type or None."""
    if isinstance(val, str):
        if _PATH_TRAVERSAL.search(val):
            return "path_traversal"
        if _check_sql(val):
            return "sql_injection"
        if _check_xss(val):
            return "xss"
    elif isinstance(val, dict):
        for v in val.values():
            result = _scan_value(v)
            if result:
                return result
    elif isinstance(val, list):
        for item in val:
            result = _scan_value(item)
            if result:
                return result
    return None


class SecurityMiddleware(BaseHTTPMiddleware):
    """Unified security middleware: injection prevention + audit trail."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        path = request.url.path

        # ── 1. Path traversal in URL ────────────────────────────────────────
        if _PATH_TRAVERSAL.search(str(request.url)):
            logger.warning("Path traversal blocked", path=path, request_id=request_id)
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "detail": "Path traversal detected"},
            )

        # ── 2. Query param scanning ─────────────────────────────────────────
        for key, value in request.query_params.items():
            threat = _scan_value(value)
            if threat:
                logger.warning(
                    f"Query param threat: {threat}",
                    key=key, path=path, request_id=request_id
                )
                return JSONResponse(
                    status_code=400,
                    content={"error": "invalid_input", "detail": f"{threat} detected in query params"},
                )

        # ── 3. Body scanning (POST/PUT/PATCH only) ──────────────────────────
        if request.method in ("POST", "PUT", "PATCH") and path not in _SKIP_VALIDATION:
            try:
                body_bytes = await request.body()
                if len(body_bytes) > _MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"error": "payload_too_large", "detail": "Request body exceeds 1 MB"},
                    )
                content_type = request.headers.get("content-type", "")
                if "application/json" in content_type and body_bytes:
                    try:
                        body_json = json.loads(body_bytes)
                        threat = _scan_value(body_json)
                        if threat:
                            logger.warning(
                                f"Body threat: {threat}",
                                path=path, request_id=request_id
                            )
                            return JSONResponse(
                                status_code=400,
                                content={"error": "invalid_input", "detail": f"{threat} detected in body"},
                            )
                    except json.JSONDecodeError:
                        pass  # Not JSON — skip
            except Exception:
                pass  # Body reading failed — skip silently

        # ── 4. Process request ──────────────────────────────────────────────
        t0 = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)

        # ── 5. Security headers ─────────────────────────────────────────────
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if response.status_code >= 400:
            response.headers["Cache-Control"] = "no-store"

        # ── 6. Audit log ────────────────────────────────────────────────────
        user_id = getattr(request.state, "user_id", None)
        logger.info(
            f"{request.method} {path} {response.status_code} {duration_ms}ms",
            request_id=request_id,
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=user_id,
            ip=request.client.host if request.client else None,
        )

        return response
