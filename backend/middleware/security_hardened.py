"""backend/middleware/security_hardened.py — Phase 12
P12-FIX-CORS-1: allow_methods explicit
P12-FIX-CORS-2: allow_headers explicit
P12-FIX-CORS-3: wildcard forbidden in production
P12-FIX-TRUST-1: TrustedHostMiddleware
P12-FIX-EXC-1,2: standardized exception handlers
P12-FIX-IP-1: X-Forwarded-For only from trusted proxies
"""
from __future__ import annotations
import ipaddress, logging, re, time, uuid
from typing import Any, Callable, Dict, List, Optional, Set
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from urllib.parse import unquote_plus
from ..core.error_codes import EC, api_error

log = logging.getLogger("middleware.security_hardened")

_ALLOWED_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
_ALLOWED_HEADERS = ["Authorization", "Content-Type", "X-Request-ID", "X-License-Key", "Accept", "Accept-Language", "Cache-Control"]
_EXPOSE_HEADERS  = ["X-Request-ID", "X-RateLimit-Remaining", "X-RateLimit-Reset"]

_RE_SQL = re.compile(r"(?i)(\bUNION\b.{0,30}\bSELECT\b|\bDROP\b.{0,20}\bTABLE\b|'\s*OR\s*'1'\s*=\s*'1|--\s*(?:$|\n)|;\s*DROP|\bEXEC\s*\(|\bSLEEP\s*\(\s*\d)")
_RE_XSS = re.compile(r"(?i)(<script[^>]{0,200}>|javascript\s*:|on\w{1,30}\s*=|<iframe[^>]{0,200}>)")
_RE_CMD = re.compile(r"(?i)(`[^`]{0,200}`|\$\([^)]{0,200}\)|\|\s*(?:sh|bash|cmd)\b|&&\s*(?:rm|curl|wget)\b)")
_RE_PATH_TRAVERSAL = re.compile(r"(?:%2e%2e|%252e%252e|\.\.[/\\]|[/\\]\.\.)" , re.IGNORECASE)
_RE_LOG_CLEAN = re.compile(r"[\r\n\t]")
_MAX_BODY_SCAN  = 64 * 1024
_INTERNAL_PATHS = ("/internal/", "/admin/db/", "/_debug/")

_SECURITY_HEADERS: Dict[str, str] = {
    "X-Content-Type-Options":       "nosniff",
    "X-Frame-Options":              "DENY",
    "X-XSS-Protection":             "1; mode=block",
    "Strict-Transport-Security":    "max-age=63072000; includeSubDomains; preload",
    "Referrer-Policy":              "strict-origin-when-cross-origin",
    "Permissions-Policy":           "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy":      "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none';",
    "Cross-Origin-Opener-Policy":   "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


def _clean(s: str) -> str:
    return _RE_LOG_CLEAN.sub(" ", s)[:200]


def _scan_text(text: str) -> Optional[str]:
    decoded = unquote_plus(text)
    if _RE_SQL.search(decoded): return "SQL_INJECTION"
    if _RE_XSS.search(decoded): return "XSS"
    if _RE_CMD.search(decoded): return "CMD_INJECTION"
    return None


def _apply_headers(response: Response, *, request_id: str, elapsed_ms: float) -> None:
    for k, v in _SECURITY_HEADERS.items():
        response.headers[k] = v
    response.headers["X-Request-ID"]    = request_id
    response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"
    try:
        del response.headers["server"]
    except KeyError:
        pass
    try:
        del response.headers["x-powered-by"]
    except KeyError:
        pass


_TRUSTED_PROXY_NETS: List[Any] = []


def configure_trusted_proxies(cidrs: str) -> None:
    global _TRUSTED_PROXY_NETS
    nets = []
    for cidr in cidrs.split(","):
        cidr = cidr.strip()
        if not cidr:
            continue
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            log.warning("Invalid trusted proxy CIDR: %s", cidr)
    _TRUSTED_PROXY_NETS = nets


def _is_trusted_proxy(ip: str) -> bool:
    if not _TRUSTED_PROXY_NETS:
        return False
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _TRUSTED_PROXY_NETS)
    except ValueError:
        return False


def get_real_ip(request: Request) -> str:
    direct_ip = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(direct_ip):
        return direct_ip
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("X-Real-IP", direct_ip)


class HardenedSecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, internal_ip_allowlist: Optional[Set[str]] = None):
        super().__init__(app)
        self._internal_ips: Set[str] = internal_ip_allowlist or {"127.0.0.1", "::1"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start      = time.monotonic()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.start_time = start
        path   = request.url.path
        method = request.method
        ip     = get_real_ip(request)

        if any(path.startswith(p) for p in _INTERNAL_PATHS):
            if ip not in self._internal_ips:
                log.warning("internal_path_blocked path=%s ip=%s", _clean(path), _clean(ip))
                err = api_error(EC.PERM_DENIED, request_id=request_id)
                return JSONResponse(err.to_response(), status_code=403, headers={"X-Request-ID": request_id})

        raw_qs = request.url.query
        if _RE_PATH_TRAVERSAL.search(path) or _RE_PATH_TRAVERSAL.search(raw_qs):
            log.warning("path_traversal path=%s ip=%s", _clean(path), _clean(ip))
            err = api_error(EC.SECURITY_PATH_TRAVERSAL, request_id=request_id)
            return JSONResponse(err.to_response(), status_code=400, headers={"X-Request-ID": request_id})

        if raw_qs:
            threat = _scan_text(raw_qs)
            if threat:
                log.warning("injection_qs threat=%s path=%s", threat, _clean(path))
                err = api_error(EC.SECURITY_INJECTION, request_id=request_id)
                return JSONResponse(err.to_response(), status_code=400, headers={"X-Request-ID": request_id})

        if method in {"POST", "PUT", "PATCH"}:
            try:
                body_bytes = await request.body()
                body_text  = body_bytes[:_MAX_BODY_SCAN].decode("utf-8", errors="replace")
                threat     = _scan_text(body_text)
                if threat:
                    log.warning("injection_body threat=%s path=%s", threat, _clean(path))
                    err = api_error(EC.SECURITY_INJECTION, request_id=request_id)
                    return JSONResponse(err.to_response(), status_code=400, headers={"X-Request-ID": request_id})
            except Exception as _e:
                log.debug("body_inspect failed: %s", type(_e).__name__)

        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled path=%s rid=%s", _clean(path), request_id)
            err  = api_error(EC.INTERNAL_ERROR, request_id=request_id)
            resp = JSONResponse(err.to_response(), status_code=500)
            _apply_headers(resp, request_id=request_id, elapsed_ms=(time.monotonic() - start) * 1000)
            return resp

        elapsed = (time.monotonic() - start) * 1000
        _apply_headers(response, request_id=request_id, elapsed_ms=elapsed)
        return response


def _validate_origins(origins: List[str], _env: str = "") -> List[str]:
    try:
        from backend.core.config import get_settings
        env = _env or get_settings().ENVIRONMENT
    except Exception:
        env = _env or "production"
    clean = []
    for o in origins:
        o = o.strip()
        if not o:
            continue
        if o == "*":
            if env == "production":
                log.error("CORS wildcard rejected in production")
                continue
            log.warning("CORS wildcard allowed (non-production)")
        clean.append(o)
    return clean or (["http://localhost:3000"] if env != "production" else [])


def apply_security_middleware(app: FastAPI, allowed_origins: List[str], trusted_hosts: List[str], trusted_proxies: str = "") -> None:
    configure_trusted_proxies(trusted_proxies)
    if trusted_hosts and trusted_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
    clean_origins = _validate_origins(allowed_origins)
    app.add_middleware(CORSMiddleware, allow_origins=clean_origins, allow_credentials=True, allow_methods=_ALLOWED_METHODS, allow_headers=_ALLOWED_HEADERS, expose_headers=_EXPOSE_HEADERS, max_age=600)
    app.add_middleware(HardenedSecurityMiddleware)


_HTTP_TO_EC: Dict[int, str] = {
    400: EC.VALIDATION_ERROR, 401: EC.AUTH_INVALID, 403: EC.PERM_DENIED,
    404: EC.NOT_FOUND, 409: EC.CONFLICT, 422: EC.VALIDATION_ERROR,
    429: EC.RATE_LIMITED, 500: EC.INTERNAL_ERROR,
    502: EC.SERVICE_UNAVAILABLE, 503: EC.SERVICE_UNAVAILABLE, 504: EC.TIMEOUT,
}


def install_exception_handlers(app: FastAPI) -> None:
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        code = _HTTP_TO_EC.get(exc.status_code, EC.INTERNAL_ERROR)
        err  = api_error(code, request_id=request_id)
        if exc.status_code < 500 and isinstance(exc.detail, str):
            err.detail = exc.detail[:200]
        elif exc.status_code < 500 and isinstance(exc.detail, dict):
            return JSONResponse(exc.detail, status_code=exc.status_code, headers={"X-Request-ID": request_id})
        return JSONResponse(err.to_response(), status_code=exc.status_code, headers={"X-Request-ID": request_id})

    @app.exception_handler(RequestValidationError)
    async def val_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        err  = api_error(EC.VALIDATION_ERROR, request_id=request_id)
        safe = [{"field": ".".join(str(l) for l in e.get("loc", [])), "msg": e.get("msg", "invalid")[:100]} for e in exc.errors()]
        resp = err.to_response()
        resp["fields"] = safe[:20]
        return JSONResponse(resp, status_code=422, headers={"X-Request-ID": request_id})

    @app.exception_handler(Exception)
    async def generic_exc(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        log.exception("unhandled rid=%s path=%s type=%s", request_id, request.url.path, type(exc).__name__)
        err = api_error(EC.INTERNAL_ERROR, request_id=request_id)
        return JSONResponse(err.to_response(), status_code=500, headers={"X-Request-ID": request_id})
