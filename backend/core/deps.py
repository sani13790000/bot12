"""
backend/core/deps.py - Merged canonical (Phase 1 + Phase 20 permission gates)

Fixes:
  A2-FIX:      get_circuit_breaker() correctly async
  A3-FIX:      get_execution_service() returns lazy singleton
  CB-NEW-5:    get_db() uses get_db_client() not AsyncSessionLocal (does not exist)
  BUG-Z2-FIX:  except ImportError: pass → logger.warning() in all permission gates
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .logger import AuditLogger, ContextualLogger, get_audit_logger, get_logger

logger = logging.getLogger("core.deps")
_bearer = HTTPBearer(auto_error=False)


# CB-NEW-5 FIX: get_db() previously imported AsyncSessionLocal which does NOT exist.
# Project uses Supabase (not SQLAlchemy). Correct getter is get_db_client().
async def get_db() -> Any:
    """Yield the Supabase database client for use in route dependencies."""
    from ..database.connection import get_db_client

    return await get_db_client()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        from .auth import verify_jwt

        _secret = get_settings().JWT_SECRET_KEY
        payload = verify_jwt(credentials.credentials, _secret)
        if not payload:
            raise ValueError("Invalid token payload")
        return payload
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_active_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get("status") in ("suspended", "banned", "deleted"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=f"Account is {user.get('status')}"
        )
    return user


async def require_admin(user: dict = Depends(get_current_active_user)) -> dict:
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return user


async def require_super_admin(user: dict = Depends(get_current_active_user)) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Super-administrator access required"
        )
    return user


# Phase 20: Permission-Based Gates


def _stub_verify_token(token: str) -> dict:
    import base64
    import json

    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Not a JWT")
        padded = parts[1] + "=" * (4 - len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


_verify_token_fn: Callable[[str], dict] = _stub_verify_token


def set_token_verifier(fn: Callable[[str], dict]) -> None:
    global _verify_token_fn
    _verify_token_fn = fn


def build_auth_context(token: str) -> Any:
    try:
        from .permissions import AuthContext, normalize_role
    except ImportError:
        raise HTTPException(status_code=500, detail="permissions module unavailable")
    try:
        payload = _verify_token_fn(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    user_id = payload.get("sub") or payload.get("user_id", "")
    raw_role = payload.get("role", "readonly")
    role = normalize_role(raw_role)
    tenant_id = payload.get("tenant_id", "default")
    is_active = bool(payload.get("is_active", True))
    is_blocked = bool(payload.get("is_blocked", False))
    plan = payload.get("plan", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing 'sub' claim")
    ctx = AuthContext(
        user_id=str(user_id),
        role=role,
        tenant_id=tenant_id,
        is_active=is_active,
        is_blocked=is_blocked,
        plan=plan,
    )
    if ctx.is_blocked:
        raise HTTPException(status_code=403, detail="Account is blocked")
    if not ctx.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")
    return ctx


def require_perm(perm: str) -> Callable:
    def _check(ctx: Any) -> Any:
        try:
            from .permissions import rbac_v2

            if not rbac_v2.check(ctx, perm):
                raise HTTPException(
                    status_code=403, detail=f"Permission '{perm}' required (role: {ctx.role})"
                )
        except ImportError as exc:
            # BUG-Z2 FIX: was bare pass — now logs warning so operators know gate is disabled
            logger.warning(
                "[deps] rbac_v2 unavailable — require_perm('%s') gate DISABLED: %s", perm, exc
            )
        return ctx

    _check.__name__ = f"perm_{perm.replace(':', '_')}"
    return _check


def require_any_perm(*perms: str) -> Callable:
    def _check(ctx: Any) -> Any:
        try:
            if not ctx.has_any_perm(*perms):
                raise HTTPException(
                    status_code=403, detail=f"One of {perms} required (role: {ctx.role})"
                )
        except (ImportError, AttributeError) as exc:
            # BUG-Z2 FIX: was bare pass — now logs warning
            logger.warning("[deps] require_any_perm%s gate DISABLED: %s", perms, exc)
        return ctx

    _check.__name__ = "any_perm"
    return _check


def require_all_perms(*perms: str) -> Callable:
    def _check(ctx: Any) -> Any:
        try:
            from .permissions import rbac_v2

            missing = [p for p in perms if not rbac_v2.check(ctx, p)]
            if missing:
                raise HTTPException(
                    status_code=403, detail=f"Missing permissions: {missing} (role: {ctx.role})"
                )
        except ImportError as exc:
            # BUG-Z2 FIX: was bare pass — now logs warning
            logger.warning(
                "[deps] rbac_v2 unavailable — require_all_perms%s gate DISABLED: %s", perms, exc
            )
        return ctx

    _check.__name__ = "all_perms"
    return _check


def require_rank(min_role: str) -> Callable:
    def _check(ctx: Any) -> Any:
        try:
            from .permissions import ROLE_RANK, normalize_role

            if ROLE_RANK.get(ctx.role, 0) < ROLE_RANK.get(normalize_role(min_role), 0):
                raise HTTPException(
                    status_code=403,
                    detail=f"Role '{min_role}' or higher required (current: {ctx.role})",
                )
        except ImportError as exc:
            # BUG-Z2 FIX: was bare pass — now logs warning
            logger.warning(
                "[deps] ROLE_RANK unavailable — require_rank('%s') gate DISABLED: %s", min_role, exc
            )
        return ctx

    _check.__name__ = f"rank_{min_role}"
    return _check


def require_no_escalation_dep(target_role: str) -> Callable:
    def _check(ctx: Any) -> Any:
        try:
            from .permissions import assert_no_escalation

            assert_no_escalation(ctx.role, target_role)
        except ImportError as exc:
            # BUG-Z2 FIX: was bare pass — now logs warning
            logger.warning(
                "[deps] assert_no_escalation unavailable — no_escalation('%s') gate DISABLED: %s",
                target_role,
                exc,
            )
        except Exception as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        return ctx

    _check.__name__ = f"no_esc_{target_role}"
    return _check


# Service accessors


async def get_risk_orchestrator_dep() -> Any:
    from ..risk.risk_orchestrator import get_risk_orchestrator

    return await get_risk_orchestrator()


def get_execution_service() -> Any:
    from ..execution.execution_service import execution_service as _es

    return _es


def get_mt5_connector() -> Any:
    from ..execution.mt5_connector import mt5_connector

    return mt5_connector


def get_metrics() -> Any:
    from ..observability.metrics import metrics_registry

    return metrics_registry


def get_audit_log() -> AuditLogger:
    return get_audit_logger()


def get_structured_logger(name: str) -> ContextualLogger:
    return get_logger(name)


async def get_circuit_breaker() -> Any:
    from ..circuit_breaker import get_mt5_breaker

    return await get_mt5_breaker()


def get_scheduler_dep() -> Any:
    from ..services.scheduler import get_scheduler

    return get_scheduler()


def get_trade_memory() -> Any:
    from ..intelligence.trade_memory import get_trade_memory as _gtm

    return _gtm()
