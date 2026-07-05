"""
backend/core/deps.py
Galaxy Vast AI Trading Platform — Dependency Injection Container (Enterprise)
"""
from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings
from .logger import get_logger, get_audit_logger, AuditLogger, ContextualLogger

_bearer = HTTPBearer(auto_error=False)


# ── Database ───────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[Any, None]:
    from ..database.connection import AsyncSessionLocal  # type: ignore[attr-defined]
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Auth ────────────────────────────────────────────────────────────────────

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
        from .auth import verify_jwt  # type: ignore[attr-defined]
        from .config import get_settings as _gs
        _secret = _gs().JWT_SECRET_KEY
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


async def get_current_active_user(
    user: dict = Depends(get_current_user),
) -> dict:
    if user.get("status") in ("suspended", "banned", "deleted"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.get('status')}",
        )
    return user


async def require_admin(
    user: dict = Depends(get_current_active_user),
) -> dict:
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


async def require_super_admin(
    user: dict = Depends(get_current_active_user),
) -> dict:
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super-administrator access required",
        )
    return user


# ── Risk ────────────────────────────────────────────────────────────────────

async def get_risk_orchestrator_dep() -> Any:
    from ..risk.risk_orchestrator import get_risk_orchestrator
    return await get_risk_orchestrator()


# ── Execution ─────────────────────────────────────────────────────────────────

def get_execution_service() -> Any:
    from ..execution.execution_service import execution_service as _es
    return _es


def get_mt5_connector() -> Any:
    from ..execution.mt5_connector import mt5_connector
    return mt5_connector


# ── Observability ───────────────────────────────────────────────────────────────

def get_metrics() -> Any:
    from ..observability.metrics import metrics_registry
    return metrics_registry


def get_audit_log() -> AuditLogger:
    return get_audit_logger()


def get_structured_logger(name: str) -> ContextualLogger:
    return get_logger(name)


# ── Infrastructure ─────────────────────────────────────────────────────────────

def get_circuit_breaker() -> Any:
    from ..circuit_breaker import get_mt5_breaker
    return get_mt5_breaker()


def get_scheduler_dep() -> Any:
    from ..services.scheduler import get_scheduler
    return get_scheduler()


def get_trade_memory() -> Any:
    from ..intelligence.trade_memory import get_trade_memory as _gtm
    return _gtm()
