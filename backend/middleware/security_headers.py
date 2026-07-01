"""Auto-repaired placeholder - original had syntax errors."""
from __future__ import annotations
import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from typing import Callable

# TODO: Original file had syntax errors that could not be auto-repaired.
# File: backend/middleware/security_headers.py

def _detect_injection(value: str):
    """Stub injection detector."""
    import re
    patterns = [r'(?i)(select|insert|update|delete|drop|union|exec)\b', r'<script', r'javascript:']
    for p in patterns:
        if re.search(p, value):
            return p
    return None

_blocked_ips: set = set()

def block_ip(ip: str) -> None:
    _blocked_ips.add(ip)

def unblock_ip(ip: str) -> None:
    _blocked_ips.discard(ip)

def blocked_ips() -> set:
    return set(_blocked_ips)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, environment: str = 'development', allowed_origins=None, enable_csp_nonce: bool = False):
        super().__init__(app)
        self._env = environment
        self._origins = allowed_origins or []
        self._enable_csp_nonce = enable_csp_nonce

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        nonce = secrets.token_hex(16)
        if self._enable_csp_nonce:
            request.state.csp_nonce = nonce
        client_ip = request.client.host if request.client else ''
        if client_ip in _blocked_ips:
            from starlette.responses import JSONResponse
            return JSONResponse({'detail': 'Forbidden'}, status_code=403)
        for k, v in request.query_params.items():
            if _detect_injection(v):
                from starlette.responses import JSONResponse
                return JSONResponse({'detail': 'Bad Request'}, status_code=400)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['X-Request-ID'] = nonce
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        if self._env == 'production':
            response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
        csp = f"default-src 'self'; script-src 'self' 'nonce-{nonce}'; frame-ancestors 'none'"
        response.headers['Content-Security-Policy'] = csp
        return response
