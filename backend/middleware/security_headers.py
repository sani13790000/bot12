"""
backend/middleware/security_headers.py
Galaxy Vast AI — Security Headers Middleware (Phase 11)
NOTE: Auto-repaired stub due to binary corruption.
"""
from __future__ import annotations
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
import re

_LOG = logging.getLogger(__name__)
_BLOCKED_IPS: set = set()
_INJECTION_RE = re.compile(
    r'(\b(select|insert|update|delete|drop|union|exec|execute)\b'
    r'|<script|javascript:|on\w+=|--\s*$|;\s*(drop|select))',
    re.IGNORECASE,
)


def _detect_injection(value: str):
    m = _INJECTION_RE.search(value)
    return m.group(0) if m else None


def block_ip(ip: str) -> None:
    _BLOCKED_IPS.add(ip)


def unblock_ip(ip: str) -> None:
    _BLOCKED_IPS.discard(ip)


def blocked_ips():
    return frozenset(_BLOCKED_IPS)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Security headers middleware."""

    def __init__(self, app, environment: str = 'production',
                 allowed_origins=None, ws_origins=None,
                 csp_report_uri=None, enable_csp_nonce: bool = True) -> None:
        super().__init__(app)
        self._env = environment
        self._origins = frozenset(allowed_origins or [])
        self._is_prod = environment == 'production'
        self._nonce_en = enable_csp_nonce

    async def dispatch(self, request: Request, call_next) -> Response:
        import uuid, secrets
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        request.state.request_id = request_id
        client_ip = (request.client.host if request.client else '0.0.0.0')
        if client_ip in _BLOCKED_IPS:
            from starlette.responses import JSONResponse
            return JSONResponse({'error': 'BLOCKED'}, status_code=403)
        for key, value in request.query_params.items():
            if _detect_injection(value) or _detect_injection(key):
                from starlette.responses import JSONResponse
                return JSONResponse({'error': 'BAD_REQUEST', 'request_id': request_id}, status_code=400)
        nonce = secrets.token_urlsafe(16) if self._nonce_en else ''
        request.state.csp_nonce = nonce
        response = await call_next(request)
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        if self._is_prod:
            response.headers['Strict-Transport-Security'] = 'max-age=63072000; includeSubDomains; preload'
        return response

    def get_csp_policy(self, nonce: str = '') -> str:
        nd = f"'nonce-{nonce}'" if nonce else ''
        return f"default-src 'self'; script-src 'self' {nd}; frame-ancestors 'none'"

    @staticmethod
    def _bad_request(request_id: str) -> Response:
        import json as _json
        return Response(
            content=_json.dumps({'error': 'BAD_REQUEST', 'request_id': request_id}),
            status_code=400,
            media_type='application/json',
        )
