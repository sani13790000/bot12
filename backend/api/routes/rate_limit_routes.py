"""
backend/api/routes/rate_limit_routes.py - Phase 22
Admin routes for rate limit management and monitoring.
"""
from __future__ import annotations
import time
from typing import List
from backend.core.rate_limit_v22 import (
    RateLimitTier, TIER_LIMITS, ENDPOINT_LIMITS, get_rate_limiter,
)


class RateLimitAdminRouter:
    def __init__(self, limiter=None):
        self._limiter = limiter or get_rate_limiter()

    def get_stats(self) -> dict:
        return self._limiter.stats()

    def list_bans(self) -> List[dict]:
        bans = self._limiter._store.list_bans()
        return [{"ip": b.ip, "reason": b.reason,
                 "abuse_type": b.abuse_type.value if b.abuse_type else None,
                 "expires_in": max(0.0, b.expires_at - time.monotonic())}
                for b in bans]

    def ban_ip(self, ip: str, reason: str, ttl: int = 3600) -> dict:
        self._limiter.ban(ip, reason, ttl)
        return {"banned": ip, "reason": reason, "ttl": ttl}

    def unban_ip(self, ip: str) -> dict:
        ok = self._limiter.unban(ip)
        return {"unbanned": ip, "was_banned": ok}

    def reset_key(self, key: str) -> dict:
        self._limiter.reset(key)
        return {"reset": key}

    def get_tiers(self) -> dict:
        return {tier.value: {"rpm": cfg.rpm, "burst": cfg.burst,
                             "ban_threshold": cfg.ban_threshold}
                for tier, cfg in TIER_LIMITS.items()}

    def get_endpoints(self) -> dict:
        return {path: {"requests": cfg.requests, "window": cfg.window,
                       "burst": cfg.burst, "reason": cfg.reason}
                for path, cfg in ENDPOINT_LIMITS.items()}

    def simulate_check(self, ip: str, endpoint: str = "/",
                       tier: str = "anonymous") -> dict:
        t = RateLimitTier(tier)
        result = self._limiter.check(ip=ip, endpoint=endpoint, tier=t)
        return {"allowed": result.allowed, "remaining": result.remaining,
                "retry_after": result.retry_after, "reason": result.reason,
                "banned": result.banned}
