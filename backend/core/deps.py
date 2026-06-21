"""
core/deps.py -- FastAPI Dependency Injection Container
Phase D Fix (ARCH-10 / TECH-2):
  - get_agent_service() now uses module singleton from agent_service.py
  - get_voting_engine() receives real 7-agent list from AgentService.agents
  - DecisionService injected with agents (DIP)
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.core.config import settings  # noqa: F401
from backend.core.security import validate_access_token
from backend.core.logger import get_logger

decode_access_token = validate_access_token

logger = get_logger("core.deps")

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
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
    if user.get("role") not in ("admin", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


@lru_cache(maxsize=1)
def get_agent_service():
    """
    FIX ARCH-10: uses module-level singleton from agent_service.py
    instead of creating a new AgentService() per DI resolution.
    """
    from backend.agents.agent_service import get_agent_service as _get
    return _get()


@lru_cache(maxsize=1)
def get_voting_engine():
    """
    FIX TECH-2: VotingEngine now receives real agents from AgentService.
    Previously VotingEngine() was called with no agents -> silent zero-score.
    """
    from backend.agents.voting_engine import VotingEngine
    agent_svc = get_agent_service()
    agents = getattr(agent_svc, "agents", None) or []
    if not agents:
        logger.warning("get_voting_engine: empty agents list")
    engine = VotingEngine(agents=agents) if agents else VotingEngine()
    logger.info("VotingEngine init with %d agents", len(agents))
    return engine


@lru_cache(maxsize=1)
def get_decision_service():
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


CurrentUser         = Annotated[dict, Depends(get_current_user)]
CurrentAdmin        = Annotated[dict, Depends(get_current_admin)]
AgentServiceDep     = Annotated[object, Depends(get_agent_service)]
VotingEngineDep     = Annotated[object, Depends(get_voting_engine)]
DecisionServiceDep  = Annotated[object, Depends(get_decision_service)]
AnalyticsServiceDep = Annotated[object, Depends(get_analytics_service)]
CacheDep            = Annotated[object, Depends(get_cache)]
RiskServiceDep      = Annotated[object, Depends(get_risk_service)]
