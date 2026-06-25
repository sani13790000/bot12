from __future__ import annotations
from typing import AsyncGenerator, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .config import get_settings
from .logger import get_logger, get_audit_logger, AuditLogger, ContextualLogger

_bearer = HTTPBearer(auto_error=False)

async def get_db() -> AsyncGenerator:
    from ..database.connection import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback(); raise
        finally:
            await session.close()

async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> dict:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authorization header missing', headers={'WWW-Authenticate': 'Bearer'})
    try:
        from .auth import verify_token
        payload = verify_token(credentials.credentials)
        if not payload: raise ValueError('Invalid token payload')
        return payload
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f'Invalid authentication: {exc}', headers={'WWW-Authenticate': 'Bearer'}) from exc

async def get_current_active_user(user: dict = Depends(get_current_user)) -> dict:
    if user.get('status') in ('suspended', 'banned', 'deleted'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Account is {user.get('status')}")
    return user

async def require_admin(user: dict = Depends(get_current_active_user)) -> dict:
    if user.get('role') not in ('admin', 'super_admin'):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Administrator access required')
    return user

async def require_super_admin(user: dict = Depends(get_current_active_user)) -> dict:
    if user.get('role') != 'super_admin':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Super-administrator access required')
    return user

async def get_risk_orchestrator_dep():
    from ..risk.risk_orchestrator import get_risk_orchestrator
    return await get_risk_orchestrator()

def get_execution_service():
    from ..execution.execution_service import get_execution_service as _ges
    return _ges()

def get_mt5_connector():
    from ..execution.mt5_connector import mt5_connector
    return mt5_connector

def get_metrics():
    from ..observability.metrics import metrics_registry
    return metrics_registry

def get_audit_log() -> AuditLogger:
    return get_audit_logger()

def get_structured_logger(name: str) -> ContextualLogger:
    return get_logger(name)

def get_circuit_breaker():
    from ..circuit_breaker import get_mt5_breaker
    return get_mt5_breaker()

def get_scheduler_dep():
    from ..services.scheduler import get_scheduler
    return get_scheduler()

def get_settings_dep():
    return get_settings()

def get_mt5_retry_config():
    from .retry import MT5_RETRY
    return MT5_RETRY

def get_db_retry_config():
    from .retry import DB_RETRY
    return DB_RETRY
