from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..core.rbac import PermissionDeniedError, Role, normalize_role, _ROLE_RANK
from ..core.audit_log import audit_logger

logger = logging.getLogger("middleware.rbac")

_ROUTE_ROLE_MAP = [
    ("/api/v1/admin",         Role.ADMIN),
    ("/api/v1/license/admin", Role.ADMIN),
    ("/api/v1/users/admin",   Role.ADMIN),
    ("/api/v1/audit",         Role.SUPPORT),
    ("/api/v1/risk/report",   Role.SUPPORT),
    ("/dashboard",            Role.ADMIN),
    ("/admin",                Role.ADMIN),
]

_PUBLIC_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
)


def _extract_role_from_request(request: Request) -> str:
    return getattr(request.state, "role", Role.READONLY)


def _get_client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RBACMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        ip   = _get_client_ip(request)

        if any(path.startswith(p) for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        required_role = None
        for prefix, role in _ROUTE_ROLE_MAP:
            if path.startswith(prefix):
                required_role = role
                break

        if required_role is not None:
            actual_role = _extract_role_from_request(request)
            actual_rank = _ROLE_RANK.get(normalize_role(actual_role), 0)
            min_rank    = _ROLE_RANK.get(required_role, 0)

            if actual_rank < min_rank:
                user_id = getattr(request.state, "user_id", None)
                logger.warning("[RBAC-MW] 403 path=%s role=%s required=%s ip=%s",
                               path, actual_role, required_role, ip)
                audit_logger.perm_denied(
                    user_id=user_id or "anonymous",
                    perm=f"role>={required_role}",
                    path=path, ip=ip,
                )
                return JSONResponse(
                    status_code=403,
                    content={"detail": f"Requires role '{required_role}' or higher"},
                )

        try:
            response = await call_next(request)
            return response
        except PermissionDeniedError as exc:
            user_id = getattr(request.state, "user_id", None)
            audit_logger.perm_denied(
                user_id=user_id or "anonymous", perm="unknown", path=path, ip=ip,
            )
            logger.warning("[RBAC-MW] PermissionDeniedError: %s", exc)
            return JSONResponse(status_code=403, content={"detail": str(exc)})
