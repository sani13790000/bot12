"""
core/deps.py -- FastAPI Dependency Injection Container
Phase D Fix (ARCH-10 / TECH-2):
  - get_voting_engine() now initialises VotingEngine WITH agents from AgentService
    (previously returned an empty VotingEngine() with no agents -> silent zero-vote decisions)
  - All singletons use lru_cache(maxsize=1) for process-level caching
  - DecisionService injected with agents (DIP)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import settings  # noqa: F401 kept for backward compat
from backend.core.security import validate_access_token
from backend.core.logger import get_logger

# backward-compat alias used by older routes
decode_access_token = validate_access_token

logger = get_logger("core.deps")

# -- Auth Bearer --
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """
    Validate JWT Bearer token and return the decoded payload.
    Raises HTTP 401 on missing/invalid token.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = validate_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


async def get_current_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require role == 'admin'."""
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# -- Service Singletons (lazy, process-level) --

@lru_cache(maxsize=1)
def get_agent_service():
    """
    Returns the global AgentService singleton.
    AgentService owns agent instances + their weights.
    """
    from backend.agents.agent_service import AgentService
    return AgentService()


@lru_cache(maxsize=1)
def get_voting_engine():
    """
    Returns a VotingEngine initialised with the full agent set from AgentService.

    FIX (ARCH-10 / TECH-2): Previously returned VotingEngine() with NO agents,
    causing every vote to produce score=0 and direction=NEUTRAL silently.
    Now we pull agents from AgentService so weights are normalised correctly.
    """
    from backend.agents.voting_engine import VotingEngine

    agent_svc = get_agent_service()
    agents = getattr(agent_svc, "agents", None) or []

    if not agents:
        logger.warning(
            "get_voting_engine: AgentService returned empty agents list -- "
            "VotingEngine will produce zero-score decisions. "
            "Check agent_service.py configuration."
        )

    engine = VotingEngine(agents=agents) if agents else VotingEngine()
    logger.info(
        "VotingEngine initialised with %d agents: %s",
        len(agents),
        [type(a).__name__ for a in agents],
    )
    return engine


@lru_cache(maxsize=1)
def get_decision_service():
    """
    Returns a DecisionService with agents injected (DIP).
    Avoids DecisionService creating its own agent instances internally.
    """
    from backend.services.decision_service import DecisionService

    agent_svc = get_agent_service()
    agents = getattr(agent_svc, "agents", None) or []
    return DecisionService(agents=agents)


@lru_cache(maxsize=1)
def get_analytics_service():
    from backend.analytics.analytics_service import AnalyticsService
    return AnalyticsService()


@lru_cache(maxsize=1)
def get_cache():
    # FIX: was 'from backend.cache import Cache' -> ImportError
    from backend.core.cache import Cache
    return Cache()


@lru_cache(maxsize=1)
def get_risk_service():
    try:
        from backend.risk.risk_orchestrator import RiskOrchestrator
        return RiskOrchestrator()
    except ImportError:
        logger.warning("RiskOrchestrator not available")
        return None


# -- Annotated dependency aliases --
CurrentUser         = Annotated[dict, Depends(get_current_user)]
CurrentAdmin        = Annotated[dict, Depends(get_current_admin)]
AgentServiceDep     = Annotated[object, Depends(get_agent_service)]
VotingEngineDep     = Annotated[object, Depends(get_voting_engine)]
DecisionServiceDep  = Annotated[object, Depends(get_decision_service)]
AnalyticsServiceDep = Annotated[object, Depends(get_analytics_service)]
CacheDep            = Annotated[object, Depends(get_cache)]
RiskServiceDep      = Annotated[object, Depends(get_risk_service)]
