"""
backend/middleware/security_headers.py
Galaxy Vast AI — Security Headers Middleware
"""
from __future__ import annotations
import logging, re, secrets, uuid
from typing import Callable, Optional, Set
logger = logging.getLogger(__name__)
_BLOCKED_IPS: Set[str] = set()
_SQL = re.compile(r"(select\s+\*|drop\s+table|insert\s+into|delete\s+from|union\s+select)", re.IGNORECASE)
_XSS = re.compile(r"(<script|javascript:|on\w+\s*=|<iframe)", re.IGNORECASE)
def block_ip(ip): _BLOCKED_IPS.add(ip)
def unblock_ip(ip): _BLOCKED_IPS.discard(ip)
def blocked_ips(): return set(_BLOCKED_IPS)
def _detect_injection(v):
    if _SQL.search(v): return "sql"
    if _XSS.search(v): return "xss"
    return None
class SecurityHeadersMiddleware:
    def __init__(self, app, *, environment="development", allowed_origins=None, enable_csp_nonce=False):
        self._app=app; self._env=environment; self._origins=allowed_origins or []; self._nonce=enable_csp_nonce
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self._app(scope, receive, send); return
        qs = scope.get("query_string", b"").decode("utf-8", errors="ignore")
        if qs and _detect_injection(qs):
            from starlette.responses import JSONResponse
            await JSONResponse({"error":"Bad Request"}, status_code=400)(scope, receive, send); return
        client = scope.get("client")
        if client and client[0] in _BLOCKED_IPS:
            from starlette.responses import JSONResponse
            await JSONResponse({"error":"Forbidden"}, status_code=403)(scope, receive, send); return
        nonce = secrets.token_hex(16) if self._nonce else ""
        class _S: pass
        state = _S(); state.csp_nonce = nonce; scope["state"] = state
        rid = str(uuid.uuid4())
        is_secure = self._env in ("production", "staging")
        hdrs = [
            (b"X-Content-Type-Options", b"nosniff"),
            (b"X-Frame-Options", b"DENY"),
            (b"Referrer-Policy", b"strict-origin-when-cross-origin"),
            (b"X-Request-ID", rid.encode()),
            (b"Permissions-Policy", b"geolocation=(), microphone=(), camera=()"),
        ]
        if is_secure: hdrs.append((b"Strict-Transport-Security", b"max-age=63072000; includeSubDomains; preload"))
        n = f" 'nonce-{nonce}'" if nonce else ""
        hdrs.append((b"Content-Security-Policy", f"default-src 'self'{n}; frame-ancestors 'none'".encode()))
        async def _s(msg):
            if msg["type"]=="http.response.start":
                msg["headers"]=list(msg.get("headers",[]))+hdrs
            await send(msg)
        try:
            await self._app(scope, receive, _s)
        except Exception:
            from starlette.responses import JSONResponse
            await JSONResponse({"error":"Internal Server Error"}, status_code=500)(scope, receive, _s)
