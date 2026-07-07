"""
backend/api/routes/rate_limit_routes.py - Phase 22
Admin routes for rate limit management and monitoring.

Phase AH fix: BUG-AH2 — added APIRouter + @router decorators
(was class RateLimitAdminRouter only — no router attr → AttributeError in main.py L155)
"""

from __future__ import annotations

import time
from typing import List

from fastapi import APIRouter, Depends

from backend.core.deps import get_current_user
from backend.core.rate_limit_v22 import (
    ENDPOINT_LIMITS,
    TIER_LIMITS,
    RateLimitTier,
    get_rate_limiter,
)

router = APIRouter(tags=["Rate Limit"])

_limiter = None


def _get_limiter():
    global _limiter
    if _limiter is None:
        _limiter = get_rate_limiter()
    return _limiter


@router.get("/stats")
async def get_stats(_user=Depends(get_current_user)) -> dict:
    """Rate limit statistics."""
    return _get_limiter().stats()


@router.get("/bans")
async def list_bans(_user=Depends(get_current_user)) -> List[dict]:
    """List all active IP bans."""
    bans = _get_limiter()._store.list_bans()
    return [
        {
            "ip": b.ip,
            "reason": b.reason,
            "abuse_type": b.abuse_type.value if b.abuse_type else None,
            "expires_in": max(0.0, b.expires_at - time.monotonic()),
        }
        for b in bans
    ]


@router.post("/ban/{ip}")
async def ban_ip(ip: str, reason: str, ttl: int = 3600, _user=Depends(get_current_user)) -> dict:
    """Ban an IP address."""
    _get_limiter().ban(ip, reason, ttl)
    return {"banned": ip, "reason": reason, "ttl": ttl}


@router.delete("/ban/{ip}")
async def unban_ip(ip: str, _user=Depends(get_current_user)) -> dict:
    """Unban an IP address."""
    ok = _get_limiter().unban(ip)
    return {"unbanned": ip, "was_banned": ok}


@router.delete("/reset/{key}")
async def reset_key(key: str, _user=Depends(get_current_user)) -> dict:
    """Reset rate limit counter for a key."""
    _get_limiter().reset(key)
    return {"reset": key}


@router.get("/tiers")
async def get_tiers(_user=Depends(get_current_user)) -> dict:
    """List all rate limit tiers and their configuration."""
    return {
        tier.value: {"rpm": cfg.rpm, "burst": cfg.burst, "ban_threshold": cfg.ban_threshold}
        for tier, cfg in TIER_LIMITS.items()
    }


@router.get("/endpoints")
async def get_endpoints(_user=Depends(get_current_user)) -> dict:
    """List endpoint-specific rate limits."""
    return {
        path: {
            "requests": cfg.requests,
            "window": cfg.window,
            "burst": cfg.burst,
            "reason": cfg.reason,
        }
        for path, cfg in ENDPOINT_LIMITS.items()
    }


@router.post("/simulate")
async def simulate_check(
    ip: str, endpoint: str = "/", tier: str = "anonymous", _user=Depends(get_current_user)
) -> dict:
    """Simulate a rate limit check without consuming quota."""
    t = RateLimitTier(tier)
    result = _get_limiter().check(ip=ip, endpoint=endpoint, tier=t)
    return {
        "allowed": result.allowed,
        "remaining": result.remaining,
        "retry_after": result.retry_after,
        "reason": result.reason,
        "banned": result.banned,
    }
