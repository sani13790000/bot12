"""FastAPI dependency injection for Galaxy Vast AI Trading Platform.

Centralizes:
- DB client injection
- Current user extraction
- Admin guard
- Service singletons
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated, Optional

from fastapi import Cookie, Depends, Header, HTTPException, status

from backend.core.config import settings
from backend.core.security import decode_access_token

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
async def get_db():
    """Yield the Supabase client."""
    from backend.database.connection import get_db_client
    return await get_db_client()


DbDep = Annotated[object, Depends(get_db)]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def _extract_token(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    access_token: Optional[str] = Cookie(None),
) -> str:
    """Extract JWT from Authorization header or HttpOnly cookie."""
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    if access_token:
        return access_token
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    token: Annotated[str, Depends(_extract_token)],
    db=Depends(get_db),
) -> dict:
    """Decode JWT, check revocation, return user payload."""
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Revocation check
    jti = payload.get("jti", "")
    if jti:
        try:
            result = await db.table("revoked_tokens").select("jti").eq("jti", jti).execute()
            if result.data:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("Revocation check failed (allowing): %s", exc)

    return payload


CurrentUser = Annotated[dict, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> dict:
    """Require admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


AdminUser = Annotated[dict, Depends(require_admin)]


# ---------------------------------------------------------------------------
# Service Singletons (lazy)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def get_agent_service():
    from backend.agents.agent_service import AgentService
    return AgentService()


@lru_cache(maxsize=1)
def get_voting_engine():
    from backend.agents.voting_engine import VotingEngine
    return VotingEngine()


@lru_cache(maxsize=1)
def get_analytics_service():
    from backend.analytics.analytics_service import AnalyticsService
    return AnalyticsService()


@lru_cache(maxsize=1)
def get_cache():
    from backend.cache import Cache
    return Cache()


AgentServiceDep = Annotated[object, Depends(get_agent_service)]
VotingEngineDep = Annotated[object, Depends(get_voting_engine)]
AnalyticsServiceDep = Annotated[object, Depends(get_analytics_service)]
CacheDep = Annotated[object, Depends(get_cache)]
