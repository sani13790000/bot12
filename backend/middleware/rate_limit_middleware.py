"""
backend/middleware/rate_limit_middleware.py - Phase 22
P22-MW-1: ASGI-compatible middleware
P22-MW-2: Extracts real IP from proxy headers
P22-MW-3: Injects X-RateLimit-* response headers
P22-MW-4: Returns 429 with Retry-After + JSON body
P22-MW-5: Tier resolved from JWT claims
P22-MW-6: Records auth failures and errors for abuse detection
"""
from __future__ import annotations

import json
import time
from typing import Dict, Optional

from backend.core.rate_limit_v22 import (
    RateLimiter, RateLimitTier, get_rate_limiter,
    make_rate_limit_headers, WHITELIST_PREFIXES,
)

_IP_HEADERS = ("X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP", "X-Client-IP")

_ROLE_TIER: Dict[str, RateLimitTier] = {
    "super_admin": RateLimitTier.ADMIN,
    "admin":       RateLimitTier.ADMIN,
    "write_admin": RateLimitTier.ADMIN,
    "support":     RateLimitTier.PRO,
    "customer":    RateLimitTier.BASIC,
    "readonly":    RateLimitTier.READONLY,
}

_PLAN_TIER: Dict[str, RateLimitTier] = {
    "vip":    RateLimitTier.VIP,
    "pro":    RateLimitTier.PRO,
    "basic":  RateLimitTier.BASIC,
    "trial":  RateLimitTier.TRIAL,
    "annual": RateLimitTier.VIP,
}

_TIER_RANK = {
    RateLimitTier.ANONYMOUS: 0, RateLimitTier.READONLY: 1,
    RateLimitTier.TRIAL: 2,     RateLimitTier.BASIC: 3,
    RateLimitTier.PRO: 4,       RateLimitTier.VIP: 5,
    RateLimitTier.ADMIN: 6,     RateLimitTier.INTERNAL: 7,
}


def extract_ip(scope: dict) -> str:
    headers = dict(scope.get("headers", []))
    for h in _IP_HEADERS:
        val = headers.get(h.lower().encode(), b"").decode()
        if val:
            return val.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else "unknown"


def resolve_tier(scope: dict) -> tuple:
    state = scope.get("state", {})
    _get  = lambda k: getattr(state, k, None) if not isinstance(state, dict) else state.get(k)
    role  = _get("role")
    plan  = _get("plan")
    uid   = _get("user_id")
    tid   = _get("tenant_id")
    tier  = RateLimitTier.ANONYMOUS
    if plan and plan in _PLAN_TIER:
        plan_tier = _PLAN_TIER[plan]
        if _TIER_RANK[plan_tier] > _TIER_RANK[tier]:
            tier = plan_tier
    if role and role in _ROLE_TIER:
        role_tier = _ROLE_TIER[role]
        if _TIER_RANK[role_tier] > _TIER_RANK[tier]:
            tier = role_tier
    return tier, uid, tid


class RateLimitMiddleware:
    def __init__(self, app, limiter: Optional[RateLimiter] = None) -> None:
        self._app     = app
        self._limiter = limiter or get_rate_limiter()

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return
        path = scope.get("path", "/")
        for prefix in WHITELIST_PREFIXES:
            if path.startswith(prefix):
                await self._app(scope, receive, send)
                return
        ip             = extract_ip(scope)
        tier, uid, tid = resolve_tier(scope)
        result = self._limiter.check(ip=ip, endpoint=path,
                                     user_id=uid, tenant_id=tid, tier=tier)
        if result.allowed:
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    for k, v in make_rate_limit_headers(result, result.limit).items():
                        headers.append((k.encode(), v.encode()))
                    message = {**message, "headers": headers}
                    status = message.get("status", 200)
                    if status >= 400:
                        self._limiter.record_error(ip)
                    if status in (401, 403):
                        self._limiter.record_auth_fail(ip)
                await send(message)
            await self._app(scope, receive, send_with_headers)
        else:
            body = json.dumps({
                "error":       "rate_limit_exceeded",
                "message":     result.reason,
                "retry_after": int(result.retry_after) + 1,
                "banned":      result.banned,
                "request_id":  result.request_id,
            }).encode()
            headers = [
                (b"content-type",   b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ]
            for k, v in make_rate_limit_headers(result, result.limit).items():
                headers.append((k.encode(), v.encode()))
            await send({"type": "http.response.start", "status": 429, "headers": headers})
            await send({"type": "http.response.body", "body": body, "more_body": False})
