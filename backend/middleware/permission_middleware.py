"""
backend/middleware/permission_middleware.py — Phase 20
=======================================================
P20-MW-1: Every non-public path checked against ENDPOINT_REGISTRY
P20-MW-2: PermissionDeniedError → 403 (never 500)
P20-MW-3: Unknown paths → 404 (not permission error)
P20-MW-4: Escalation attempts → 403 + audit
P20-MW-5: Blocked/inactive account → 403 on every request
"""
from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from ..core.permissions import (
    AuthContext,
    ENDPOINT_REGISTRY,
    EndpointSpec,
    P,
    PermissionDeniedError,
    rbac_v2,
)

logger = logging.getLogger("middleware.perm_v2")

# Public paths — no auth required
PUBLIC_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
)


def _match_endpoint(method: str, path: str) -> Optional[EndpointSpec]:
    """
    Match HTTP method + path to ENDPOINT_REGISTRY.
    Supports {param} placeholders.
    Returns None if no match.
    """
    for ep in ENDPOINT_REGISTRY:
        if ep.method.upper() != method.upper():
            continue
        # Exact match
        if ep.path == path:
            return ep
        # Template match: /api/v1/trades/{trade_id}
        ep_parts   = ep.path.split("/")
        path_parts = path.split("/")
        if len(ep_parts) != len(path_parts):
            continue
        match = all(
            ep_seg.startswith("{") and ep_seg.endswith("}")
            or ep_seg == path_seg
            for ep_seg, path_seg in zip(ep_parts, path_parts)
        )
        if match:
            return ep
    return None


class PermissionEnforcer:
    """
    Stateless enforcer — call check() before each route handler.
    Used by middleware and by route-level guards.
    """

    def check(
        self,
        method: str,
        path: str,
        ctx: Optional[AuthContext],
    ) -> Tuple[bool, str]:
        """
        Returns (allowed: bool, reason: str).
        allowed=True  → proceed
        allowed=False → return 403 with reason
        """
        # Public prefix bypass
        if any(path.startswith(p) for p in PUBLIC_PREFIXES):
            return True, "public"

        ep = _match_endpoint(method, path)
        if ep is None:
            # Unknown endpoint — pass to router (→ 404)
            return True, "unknown_path"

        if ep.permission == "public":
            return True, "public_endpoint"

        if ctx is None:
            return False, "authentication_required"

        if ctx.is_blocked:
            return False, "account_blocked"

        if not ctx.is_active:
            return False, "account_inactive"

        allowed = rbac_v2.check(ctx, ep.permission)
        if not allowed:
            logger.warning(
                "[PERM-MW] 403 method=%s path=%s perm=%s user=%s role=%s",
                method, path, ep.permission,
                ctx.user_id[:8], ctx.role,
            )
            return False, f"missing_permission:{ep.permission}"

        return True, "ok"


# Singleton
enforcer = PermissionEnforcer()


# ─────────────────────────────────────────────────────────────────────────────
# Route-level decorator (for FastAPI routes without full Depends chain)
# ─────────────────────────────────────────────────────────────────────────────

def guard(perm: str):
    """
    Lightweight decorator — validates ctx.has_perm(perm).
    """
    def decorator(fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*args, ctx: AuthContext = None, **kwargs):
            if ctx is None:
                for arg in args:
                    if isinstance(arg, AuthContext):
                        ctx = arg
                        break
            if ctx is None or not rbac_v2.check(ctx, perm):
                raise PermissionDeniedError(
                    f"Permission '{perm}' required"
                )
            return fn(*args, ctx=ctx, **kwargs)
        return wrapper
    return decorator
