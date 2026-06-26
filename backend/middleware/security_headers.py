"""
backend/middleware/security_headers.py
Galaxy Vast AI — Security Headers Middleware (Phase 11)

P11-SH-1: Content-Security-Policy — strict SaaS dashboard policy
P11-SH-2: HSTS — max-age=63072000 (2 years) + preload
P11-SH-3: X-Frame-Options DENY
P11-SH-4: X-Content-Type-Options nosniff
P11-SH-5: Referrer-Policy strict-origin-when-cross-origin
P11-SH-6: Permissions-Policy — همه dangerous APIs بسته
P11-SH-7: CSP nonce per-request برای inline scripts
P11-SH-8: Report-Only mode برای staging
P11-SH-9: CORS تنها از ALLOWED_ORIGINS (هرگز wildcard در production)
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

_CSP_BASE = (
    "default-src 'self'; "
    "script-src 'self' {nonce_directive}; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https:; "
    "connect-src 'self' {ws_origins}; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "upgrade-insecure-requests"
)

_CSP_REPORT_ONLY = (
    "default-src 'self'; "
    "script-src 'self' {nonce_directive} 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self' {ws_origins}; "
    "report-uri /api/v1/csp-report"
)

_API_PATH_RE = re.compile(r"^/api/")
_BLOCKED_IPS: Set[str] = set()

_INJECTION_RE = re.compile(
    r"(\b(select|insert|update|delete|drop|union|exec|execute)\b"
    r"|<script|javascript:|on\w+=|--\s*$|;\s*(drop|select))",
    re.IGNORECASE,
)
_MAX_BODY_INSPECT = 32_768


def _detect_injection(value: str) -> Optional[str]:
    m = _INJECTION_RE.search(value)
    return m.group(0) if m else None


def _sanitise_log(value: str, max_len: int = 200) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", str(value))[:max_len]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Comprehensive security headers + injection detection middleware."""

    def __init__(
        self,
        app,
        environment: str = "production",
        allowed_origins: Optional[List[str]] = None,
        ws_origins: Optional[List[str]] = None,
        csp_report_uri: Optional[str] = None,
        enable_csp_nonce: bool = True,
    ) -> None:
        super().__init__(app)
        self._env      = environment
        self._origins  = frozenset(allowed_origins or [])
        self._ws_origins = " ".join(
            o.replace("https://", "wss://").replace("http://", "ws://")
            for o in (ws_origins or list(self._origins))
        ) or "'self'"
        self._report_uri = csp_report_uri or ""
        self._nonce_en   = enable_csp_nonce
        self._is_prod    = environment == "production"
        self._is_staging = environment == "staging"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        client_ip = (request.client.host if request.client else "0.0.0.0")
        if client_ip in _BLOCKED_IPS:
            log.warning("blocked_ip ip=%s rid=%s", client_ip, request_id)
            return self._bad_request(request_id)

        path = request.url.path

        for key, value in request.query_params.items():
            threat = _detect_injection(value) or _detect_injection(key)
            if threat:
                log.warning(
                    "injection_in_query threat=%s param=%s path=%s rid=%s",
                    threat, _sanitise_log(key), _sanitise_log(path), request_id,
                )
                return self._bad_request(request_id)

        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type and request.method in ("POST", "PUT", "PATCH"):
            try:
                body_bytes = await request.body()
                if body_bytes and len(body_bytes) <= _MAX_BODY_INSPECT:
                    body_text = body_bytes.decode("utf-8", errors="replace")
                    threat = _detect_injection(body_text)
                    if threat:
                        log.warning(
                            "injection_in_body threat=%s path=%s rid=%s",
                            threat, _sanitise_log(path), request_id,
                        )
                        return self._bad_request(request_id)
            except Exception as e:
                log.debug("body_inspect_failed: %s", type(e).__name__)

        nonce = secrets.token_urlsafe(16) if self._nonce_en else ""
        request.state.csp_nonce = nonce

        try:
            response = await call_next(request)
        except Exception as exc:
            log.error("unhandled_error path=%s rid=%s: %s", path, request_id, exc, exc_info=True)
            return Response(
                content=_json.dumps({"error": "INTERNAL_SERVER_ERROR", "request_id": request_id}),
                status_code=500,
                media_type="application/json",
            )

        self._set_headers(response, path, nonce, request_id)
        return response

    def _set_headers(self, response: Response, path: str, nonce: str, request_id: str) -> None:
        h = response.headers
        h["X-Request-ID"]           = request_id
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"]        = "DENY"
        h["X-XSS-Protection"]       = "1; mode=block"
        h["Referrer-Policy"]        = "strict-origin-when-cross-origin"
        h["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )
        if self._is_prod:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        elif self._is_staging:
            h["Strict-Transport-Security"] = "max-age=86400; includeSubDomains"

        if not _API_PATH_RE.match(path):
            nonce_directive = f"'nonce-{nonce}'" if nonce else ""
            ws = self._ws_origins
            if self._is_prod:
                csp = _CSP_BASE.format(nonce_directive=nonce_directive, ws_origins=ws)
                h["Content-Security-Policy"] = csp
            else:
                csp = _CSP_REPORT_ONLY.format(nonce_directive=nonce_directive, ws_origins=ws)
                h["Content-Security-Policy-Report-Only"] = csp

    @staticmethod
    def _bad_request(request_id: str) -> Response:
        return Response(
            content=_json.dumps({"error": "BAD_REQUEST", "request_id": request_id}),
            status_code=400,
            media_type="application/json",
        )


def block_ip(ip: str) -> None:
    _BLOCKED_IPS.add(ip)


def unblock_ip(ip: str) -> None:
    _BLOCKED_IPS.discard(ip)


def blocked_ips() -> FrozenSet[str]:
    return frozenset(_BLOCKED_IPS)
