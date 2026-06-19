"""
backend/middleware/security.py
Security middleware - production-hardened v3.

Changes:
  * Uses get_client_ip() - spoof-resistant IP extraction.
  * Internal-path protection uses PREFIX matching + IP allowlist.
  * URL decoding (unquote_plus) applied before injection scanning.
  * Body scan capped at 64 KB (_MAX_BODY_SCAN_BYTES).
  * Security headers on ALL response paths (200/400/403/500).
  * request.state.request_id + start_time always set.
  * CRLF/tab stripped from all log values.
  * All regex compiled once at module load.
"""
from __future__ import annotations

import ipaddress
import logging
import re
import time
import uuid
from typing import Awaitable, Callable
from urllib.parse import unquote_plus

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from backend.core.client_ip import get_client_ip

log = logging.getLogger(__name__)

# Max body size to scan - larger bodies passed through un-scanned.
_MAX_BODY_SCAN_BYTES: int = 64 * 1024

# All patterns compiled once at import time.
_RE_SQL = re.compile(
    r"(?i)("
    r"\bUNION\b.{0,30}\bSELECT\b"
    r"|\bDROP\b.{0,20}\bTABLE\b"
    r"|\bINSERT\b.{0,20}\bINTO\b"
    r"|\bDELETE\b.{0,20}\bFROM\b"
    r"|'\s*OR\s*'1'\s*=\s*'1"
    r"|--\s*(?:$|\n)"
    r"|;\s*DROP"
    r"|\bEXEC\s*\("
    r"|\bSLEEP\s*\(\s*\d"
    r"|\bBENCHMARK\s*\("
    r")"
)
_RE_XSS = re.compile(
    r"(?i)("
    r"<script[^>]{0,200}>"
    r"|javascript\s*:"
    r"|on\w{1,30}\s*="
    r"|<iframe[^>]{0,200}>"
    r"|<object[^>]{0,200}>"
    r"|<embed[^>]{0,200}>"
    r"|<svg[^>]{0,200}onload"
    r")"
)
_RE_CMD = re.compile(
    r"(?i)("
    r"`[^`]{0,200}`"
    r"|\$\([^)]{0,200}\)"
    r"|\|\s*(?:sh|bash|cmd|powershell|zsh|dash)\b"
    r"|&&\s*(?:sh|bash|cmd|rm|curl|wget)\b"
    r")"
)
_RE_PATH_TRAVERSAL = re.compile(
    r"(?:%2e%2e|%252e%252e|\.\.[/\\]|[/\\]\.\.)" ,
    re.IGNORECASE,
)
_RE_LOG_CLEAN = re.compile(r"[\r\n\t]")

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options":    "nosniff",
    "X-Frame-Options":           "DENY",
    "X-XSS-Protection":          "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Referrer-Policy":           "strict-origin-when-cross-origin",
    "Permissions-Policy":        "geolocation=(), microphone=(), camera=()",
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
    "Pragma":        "no-cache",
}

# Internal-path prefixes - restricted to internal IPs only.
_INTERNAL_PATH_PREFIXES: tuple[str, ...] = (
    "/metrics",
    "/internal",
    "/_debug",
    "/__debug__",
    "/admin",
    "/api/v1/observability",
    "/api/v1/metrics",
)

_INTERNAL_ALLOWED_CIDRS: tuple[str, ...] = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "::1/128",
    "fc00::/7",
)


def _build_internal_networks():
    nets = []
    for cidr in _INTERNAL_ALLOWED_CIDRS:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            log.warning("security: invalid internal CIDR %r", cidr)
    return tuple(nets)


_INTERNAL_NETWORKS = _build_internal_networks()


def _is_internal_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        for net in _INTERNAL_NETWORKS:
            try:
                if addr in net:
                    return True
            except TypeError:
                continue
    except ValueError:
        pass
    return False


def _is_internal_path(path: str) -> bool:
    for prefix in _INTERNAL_PATH_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _sanitise_log(value: str, maxlen: int = 200) -> str:
    return _RE_LOG_CLEAN.sub(" ", value)[:maxlen]


def _apply_security_headers(
    response: Response, request_id: str = "", elapsed_ms: float = 0.0
) -> None:
    for k, v in _SECURITY_HEADERS.items():
        response.headers[k] = v
    if request_id:
        response.headers["X-Request-ID"] = request_id
    if elapsed_ms:
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"


def _scan_text(text: str) -> str | None:
    """Scan URL-decoded text for injection patterns. Returns threat name or None."""
    decoded = unquote_plus(text)
    if _RE_SQL.search(decoded):
        return "sql_injection"
    if _RE_XSS.search(decoded):
        return "xss"
    if _RE_CMD.search(decoded):
        return "command_injection"
    return None


def _forbidden(request_id: str = "") -> JSONResponse:
    resp = JSONResponse({"error": "Forbidden"}, status_code=403)
    _apply_security_headers(resp, request_id=request_id)
    return resp


def _bad_request(request_id: str = "") -> JSONResponse:
    resp = JSONResponse({"error": "Bad request"}, status_code=400)
    _apply_security_headers(resp, request_id=request_id)
    return resp


def _server_error(request_id: str = "") -> JSONResponse:
    resp = JSONResponse({"error": "Internal server error"}, status_code=500)
    _apply_security_headers(resp, request_id=request_id)
    return resp


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Production security middleware.

    Check order (fast to slow):
      1. Set request.state.request_id + start_time
      2. Internal-path IP allowlist (prefix matching + real IP)
      3. Path traversal in URL + raw query string
      4. Injection scan of URL-decoded query string
      5. Injection scan of body (max 64 KB, mutating methods only)
      6. Call downstream handler
      7. Stamp security headers on ALL responses
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start      = time.monotonic()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = start

        path   = request.url.path
        method = request.method

        # 1. Internal-path IP allowlist (uses real IP, not raw header)
        if _is_internal_path(path):
            client_ip = get_client_ip(request)
            if not _is_internal_ip(client_ip):
                log.warning(
                    "internal_path_blocked path=%s ip=%s",
                    _sanitise_log(path), _sanitise_log(client_ip)
                )
                return _forbidden(request_id)

        # 2. Path traversal
        raw_qs = request.url.query
        if _RE_PATH_TRAVERSAL.search(path) or _RE_PATH_TRAVERSAL.search(raw_qs):
            log.warning(
                "path_traversal path=%s ip=%s",
                _sanitise_log(path), _sanitise_log(get_client_ip(request))
            )
            return _forbidden(request_id)

        # 3. Query-string injection scan
        if raw_qs:
            threat = _scan_text(raw_qs)
            if threat:
                log.warning("injection_in_qs threat=%s path=%s", threat, _sanitise_log(path))
                return _bad_request(request_id)

        # 4. Body injection scan (capped at 64 KB)
        if method in {"POST", "PUT", "PATCH"}:
            try:
                body_bytes = await request.body()
                body_text  = body_bytes[:_MAX_BODY_SCAN_BYTES].decode("utf-8", errors="replace")
                threat     = _scan_text(body_text)
                if threat:
                    log.warning(
                        "injection_in_body threat=%s path=%s", threat, _sanitise_log(path)
                    )
                    return _bad_request(request_id)
            except Exception:
                pass

        # 5. Call downstream
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled path=%s", _sanitise_log(path))
            return _server_error(request_id)

        # 6. Stamp security headers on the actual response
        elapsed = (time.monotonic() - start) * 1000
        _apply_security_headers(response, request_id=request_id, elapsed_ms=elapsed)
        log.debug(
            "req id=%s method=%s path=%s status=%s time=%.1fms",
            request_id, method, _sanitise_log(path), response.status_code, elapsed,
        )
        return response
