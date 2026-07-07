"""
backend/api/routes/permissions_routes.py — Phase 20
=====================================================
P20-ROUTE-PERM-1: GET /permissions/matrix  → full role×permission matrix
P20-ROUTE-PERM-2: GET /permissions/my      → current user's permissions
P20-ROUTE-PERM-3: GET /permissions/endpoints → all endpoints + required perm
P20-ROUTE-PERM-4: GET /permissions/roles   → role definitions

Phase AH fix: BUG-AH1 — added APIRouter + @router decorators
(was plain functions only — no router attr → AttributeError in main.py L154)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..core.deps import get_current_user
from ..core.deps_v3 import require_perm
from ..core.permissions import (
    ROLE_RANK,
    AuthContext,
    P,
    Role,
    expand_permissions,
    rbac_v2,
)

router = APIRouter(tags=["permissions"])


@router.get("/matrix")
async def get_matrix(_user=Depends(get_current_user)) -> dict:
    """P20-ROUTE-PERM-1. Full role×permission matrix."""
    ctx: AuthContext = _user
    require_perm(P.PROFILE_READ_OWN)(ctx)
    return rbac_v2.permission_matrix()


@router.get("/my")
async def get_my_permissions(_user=Depends(get_current_user)) -> dict:
    """P20-ROUTE-PERM-2. Current user's permissions."""
    ctx: AuthContext = _user
    require_perm(P.PROFILE_READ_OWN)(ctx)
    return {
        "user_id": ctx.user_id,
        "role": ctx.role,
        "rank": ctx.rank,
        "permissions": sorted(ctx.effective_perms - {P.ALL}),
        "plan": ctx.plan,
    }


@router.get("/endpoints")
async def get_endpoint_permissions(_user=Depends(get_current_user)) -> dict:
    """P20-ROUTE-PERM-3. All endpoints + required permission."""
    ctx: AuthContext = _user
    require_perm(P.PROFILE_READ_OWN)(ctx)
    return {
        "endpoints": rbac_v2.endpoint_permissions(),
        "total": len(rbac_v2.endpoint_permissions()),
    }


@router.get("/roles")
async def get_role_definitions(_user=Depends(get_current_user)) -> dict:
    """P20-ROUTE-PERM-4. Role definitions."""
    ctx: AuthContext = _user
    require_perm(P.PROFILE_READ_OWN)(ctx)
    roles = {}
    for role in [
        Role.READONLY,
        Role.CUSTOMER,
        Role.SUPPORT,
        Role.WRITE_ADMIN,
        Role.ADMIN,
        Role.SUPER,
    ]:
        perms = sorted(expand_permissions(role) - {P.ALL})
        roles[role] = {
            "rank": ROLE_RANK[role],
            "permissions": perms,
            "perm_count": len(perms),
        }
    return {"roles": roles}
