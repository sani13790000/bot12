"""
backend/middleware/security.py
Galaxy Vast AI — Security Middleware
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_LOG = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """Basic security middleware."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.time()
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception as exc:
            _LOG.error('unhandled_error rid=%s: %s', request_id, exc, exc_info=True)
            import json as _json
            return Response(
                content=_json.dumps({'error': 'INTERNAL_SERVER_ERROR', 'request_id': request_id}),
                status_code=500,
                media_type='application/json',
            )

        duration = time.time() - start
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Response-Time'] = f'{duration:.3f}s'
        return response
