"""
backend/middleware/security.py
Galaxy Vast AI — Security Middleware
"""
from __future__ import annotations
import logging
from typing import Any, Callable, Awaitable
logger = logging.getLogger(__name__)

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response

    class SecurityMiddleware(BaseHTTPMiddleware):
        async def dispatch(
            self,
            request: Request,
            call_next: Callable[[Request], Awaitable[Response]],
        ) -> Response:
            response = await call_next(request)
            return response
except ImportError:
    class SecurityMiddleware:  # type: ignore
        pass

__all__ = ["SecurityMiddleware"]
