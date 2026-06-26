"""
backend/api/routes/permissions_routes.py — Phase 20
=====================================================
P20-ROUTE-PERM-1: GET /permissions/matrix  → full role×permission matrix
P20-ROUTE-PERM-2: GET /permissions/my      → current user's permissions
P20-ROUTE-PERM-3: GET /permissions/endpoints → all endpoints + required perm
P20-ROUTE-PERM-4: GET /permissions/roles   → role definitions
"""
from __future__ import annotations

from ..core.permissions import (
    AuthContext,
    P,
    PERM_DESCRIPTIONS,
    Role,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    rbac_v2,
    expand_permissions,
)
from ..core.deps_v3 import require_perm


def get_matrix(ctx: AuthContext) -> dict:
    """P20-ROUTE-PERM-1."""
    require_perm(P.PROFILE_READ_OWN)(ctx)
    return rbac_v2.permission_matrix()


def get_my_permissions(ctx: AuthContext) -> dict:
    """P20-ROUTE-PERM-2."""
    require_perm(P.PROFILE_READ_OWN)(ctx)
    return {
        "user_id":    ctx.user_id,
        "role":       ctx.role,
        "rank":       ctx.rank,
        "permissions": sorted(ctx.effective_perms - {P.ALL}),
        "plan":       ctx.plan,
    }


def get_endpoint_permissions(ctx: AuthContext) -> dict:
    """P20-ROUTE-PERM-3."""
    require_perm(P.PROFILE_READ_OWN)(ctx)
    return {
        "endpoints": rbac_v2.endpoint_permissions(),
        "total": len(rbac_v2.endpoint_permissions()),
    }


def get_role_definitions(ctx: AuthContext) -> dict:
    """P20-ROUTE-PERM-4."""
    require_perm(P.PROFILE_READ_OWN)(ctx)
    roles = {}
    for role in [Role.READONLY, Role.CUSTOMER, Role.SUPPORT,
                 Role.WRITE_ADMIN, Role.ADMIN, Role.SUPER]:
        perms = sorted(expand_permissions(role) - {P.ALL})
        roles[role] = {
            "rank":        ROLE_RANK[role],
            "permissions": perms,
            "perm_count":  len(perms),
        }
    return {"roles": roles}
