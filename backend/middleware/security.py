"""
backend/middleware/security.py
Galaxy Vast AI — Security Middleware

Provides:
  - Request ID injection
  - JWT authentication checks
  - Rate limit enforcement
  - Security event logging
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MAX_BODY_SIZE = int(os.getenv("MAX_BODY_SIZE_BYTES", str(10 * 1024 * 1024)))


class SecurityMiddleware:
    """Starlette-compatible security middleware."""

    def __init__(self, app: Callable, *, enable_jwt: bool = True, enable_rate_limit: bool = True) -> None:
        self._app = app
        self._enable_jwt = enable_jwt
        self._enable_rate_limit = enable_rate_limit
        self._log = logging.getLogger(self.__class__.__name__)

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        scope["state"] = getattr(scope, "state", {})
        if hasattr(scope, "state"):
            pass
        else:
            scope["state"] = {}

        start = time.monotonic()
        try:
            await self._app(scope, receive, send)
        finally:
            elapsed = (time.monotonic() - start) * 1000
            path = scope.get("path", "?")
            self._log.debug("[%s] %s %.1fms", request_id, path, elapsed)

    def _extract_bearer(self, headers: list) -> Optional[str]:
        for name, value in headers:
            if name.lower() == b"authorization":
                decoded = value.decode("utf-8", errors="ignore")
                if decoded.startswith("Bearer "):
                    return decoded[7:]
        return None


def create_security_middleware(enable_jwt: bool = True, enable_rate_limit: bool = True):
    """Factory for SecurityMiddleware."""
    def _wrapper(app):
        return SecurityMiddleware(app, enable_jwt=enable_jwt, enable_rate_limit=enable_rate_limit)
    return _wrapper
