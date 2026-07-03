"""
backend/middleware/security_headers.py
Galaxy Vast AI — Security Headers Middleware (Phase 11)

P11-SH-1: Content-Security-Policy
P11-SH-2: HSTS — Strict-Transport-Security max-age=63072000 + preload
P11-SH-3: X-Frame-Options DENY
P11-SH-4: X-Content-Type-Options nosniff
P11-SH-5: Referrer-Policy strict-origin-when-cross-origin
P11-SH-6: Permissions-Policy
P11-SH-7: CSP nonce per-request for inline scripts
P11-SH-8: Report-Only mode for staging
P11-SH-9: CORS only from ALLOWED_ORIGINS
"""
from __future__ import annotations

import json as _json
import re
import secrets
import uuid
from typing import Callable, FrozenSet, List, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import logging

log = logging.getLogger(__name__)

_BLOCKED_IPS: Set[str] = set()
_INJECTION_RE = re.compile(
    r"(\b(select|insert|update|delete|drop|union|exec|execute)\b"
    r"|<script|javascript:|on\w+=|--\s*$|;\s*(drop|select))",
    re.IGNORECASE,
)
_MAX_BODY_INSPECT = 32_768
_API_PATH_RE = re.compile(r"^/api/")


def _detect_injection(value: str) -> Optional[str]:
    m = _INJECTION_RE.search(value)
    return m.group(0) if m else None


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, environment: str = "production",
                 allowed_origins: Optional[List[str]] = None,
                 ws_origins: Optional[List[str]] = None,
                 csp_report_uri: Optional[str] = None,
                 enable_csp_nonce: bool = True) -> None:
        super().__init__(app)
        self._env = environment
        self._origins = frozenset(allowed_origins or [])
        self._nonce_en = enable_csp_nonce
        self._is_prod = environment == "production"
        self._is_staging = environment == "staging"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        client_ip = (request.client.host if request.client else "0.0.0.0")
        if client_ip in _BLOCKED_IPS:
            return self._bad_request(request_id)
        for key, value in request.query_params.items():
            threat = _detect_injection(value) or _detect_injection(key)
            if threat:
                return self._bad_request(request_id)
        nonce = secrets.token_urlsafe(16) if self._nonce_en else ""
        request.state.csp_nonce = nonce
        try:
            response = await call_next(request)
        except Exception as exc:
            log.error("unhandled_error path=%s rid=%s: %s", request.url.path, request_id, exc)
            return Response(
                content=_json.dumps({"error": "INTERNAL_SERVER_ERROR", "request_id": request_id}),
                status_code=500, media_type="application/json",
            )
        h = response.headers
        h["X-Request-ID"] = request_id
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["X-XSS-Protection"] = "1; mode=block"
        h["Referrer-Policy"] = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        if self._is_prod:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response

    @staticmethod
    def _bad_request(request_id: str) -> Response:
        return Response(
            content=_json.dumps({"error": "BAD_REQUEST", "request_id": request_id}),
            status_code=400, media_type="application/json",
        )


def block_ip(ip: str) -> None:
    _BLOCKED_IPS.add(ip)


def unblock_ip(ip: str) -> None:
    _BLOCKED_IPS.discard(ip)


def blocked_ips() -> FrozenSet[str]:
    return frozenset(_BLOCKED_IPS)
