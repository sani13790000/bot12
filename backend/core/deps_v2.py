from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .rbac import (
    AuthContext, Perm, PermissionDeniedError, Role,
    _ROLE_RANK, normalize_role, rbac_engine,
)

logger = logging.getLogger("core.deps")
_bearer = HTTPBearer(auto_error=False)


async def _extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    access_token: Optional[str] = Cookie(default=None),
) -> str:
    token = access_token or (credentials.credentials if credentials else None)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def get_auth_context(token: str = Depends(_extract_token)) -> AuthContext:
    try:
        from .security import verify_access_token
        payload = verify_access_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    user_id    = payload.get("sub") or payload.get("user_id")
    raw_role   = payload.get("role", "readonly")
    role       = normalize_role(raw_role)
    is_active  = payload.get("is_active", True)
    is_blocked = payload.get("is_blocked", False)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject claim")
    ctx = AuthContext(user_id=str(user_id), role=role,
                     is_active=bool(is_active), is_blocked=bool(is_blocked))
    if ctx.is_blocked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is blocked")
    if not ctx.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    return ctx


async def get_current_user(ctx: AuthContext = Depends(get_auth_context)) -> dict:
    return {"sub": ctx.user_id, "id": ctx.user_id, "role": ctx.role,
            "is_active": ctx.is_active, "is_blocked": ctx.is_blocked}


def require_perm(perm: str) -> Callable:
    async def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        try:
            rbac_engine.require(ctx, perm)
        except PermissionDeniedError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return ctx
    _dep.__name__ = f"require_perm_{perm.replace(':', '_')}"
    return _dep


def require_role(min_role: str) -> Callable:
    min_rank = _ROLE_RANK.get(normalize_role(min_role), 0)
    async def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if ctx.rank < min_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role '{min_role}' or higher",
            )
        return ctx
    _dep.__name__ = f"require_role_{min_role}"
    return _dep


def require_owner(perm: str) -> Callable:
    async def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        return ctx
    _dep.__name__ = f"require_owner_{perm.replace(':', '_')}"
    return _dep


require_admin   = require_role(Role.ADMIN)
require_support = require_role(Role.SUPPORT)
require_super   = require_role(Role.SUPER)

require_read_own_trades   = require_perm(Perm.READ_OWN_TRADES)
require_read_own_signals  = require_perm(Perm.READ_OWN_SIGNALS)
require_manage_users      = require_perm(Perm.MANAGE_USERS)
require_manage_licenses   = require_perm(Perm.MANAGE_LICENSES)
require_pause_trading     = require_perm(Perm.PAUSE_TRADING)
require_close_all         = require_perm(Perm.CLOSE_ALL)
require_audit_log         = require_perm(Perm.READ_AUDIT_LOG)
