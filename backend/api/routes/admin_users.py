from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.core.deps_v2 import (
    require_admin, require_manage_users, require_audit_log,
)
from backend.core.rbac import (
    AuthContext, Perm, Role, rbac_engine,
    PermissionDeniedError, normalize_role, _ROLE_RANK,
)
from backend.core.audit_log import audit_logger
from backend.database import db

logger = logging.getLogger("api.admin_users")
# BUG-AD4b fix: was prefix='/admin/users', main.py provides prefix='/admin'
# So prefix='/users' + main prefix='/admin' = /admin/users/* (correct)
router = APIRouter(prefix="/users", tags=["Admin -- Users"])


class ChangeRoleRequest(BaseModel):
    role: str = Field(..., description="Target role name")


class BlockRequest(BaseModel):
    reason: str = Field("", max_length=500)


class UserListResponse(BaseModel):
    users:  List[dict]
    total:  int
    limit:  int
    offset: int


@router.get("/")
async def list_users(
    role:   Optional[str] = Query(None),
    limit:  int           = Query(50, ge=1, le=200),
    offset: int           = Query(0,  ge=0),
    ctx: AuthContext = Depends(require_manage_users),
) -> dict:
    filters = {}
    if role:
        filters["role"] = role
    try:
        rows = await db.select_many(
            "users", filters=filters,
            columns="id,email,role,is_active,is_blocked,created_at,updated_at",
            order_by="created_at", order_desc=True, limit=limit, offset=offset,
        )
    except Exception as exc:
        logger.error("list_users DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")
    return {"users": rows or [], "total": len(rows or []), "limit": limit, "offset": offset}


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    ctx: AuthContext = Depends(require_manage_users),
) -> dict:
    row = await db.select_one("users", {"id": user_id},
                              columns="id,email,role,is_active,is_blocked,created_at,block_reason")
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "data": row}


@router.patch("/{user_id}/role")
async def change_role(
    user_id: str,
    body:    ChangeRoleRequest,
    ctx: AuthContext = Depends(require_manage_users),
) -> dict:
    target_role = normalize_role(body.role)
    if target_role not in [r.value for r in Role]:
        raise HTTPException(status_code=400, detail=f"Unknown role: {body.role}")
    if not rbac_engine.can_escalate_to(ctx, target_role):
        raise HTTPException(status_code=403, detail=f"Cannot assign role '{target_role}' -- must be strictly below your own")
    target = await db.select_one("users", {"id": user_id}, columns="id,role")
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    old_role = target.get("role", "unknown")
    await db.update("users", {"id": user_id}, {"role": target_role})
    rbac_engine.invalidate(user_id)
    audit_logger.role_changed(target_id=user_id, old=old_role, new=target_role, actor_id=ctx.user_id)
    return {"success": True, "old_role": old_role, "new_role": target_role}


@router.post("/{user_id}/block")
async def block_user(
    user_id: str,
    body:    BlockRequest,
    ctx: AuthContext = Depends(require_manage_users),
) -> dict:
    if user_id == ctx.user_id:
        raise HTTPException(status_code=400, detail="Cannot block yourself")
    target = await db.select_one("users", {"id": user_id}, columns="id,role,is_blocked")
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.get("is_blocked"):
        return {"success": True, "message": "Already blocked"}
    target_rank = _ROLE_RANK.get(normalize_role(target.get("role", "readonly")), 0)
    if target_rank >= ctx.rank:
        raise HTTPException(status_code=403, detail="Cannot block user with equal or higher role")
    await db.update("users", {"id": user_id}, {"is_blocked": True, "block_reason": body.reason})
    rbac_engine.invalidate(user_id)
    audit_logger.user_blocked(target_id=user_id, actor_id=ctx.user_id, reason=body.reason)
    return {"success": True, "message": "User blocked"}


@router.post("/{user_id}/unblock")
async def unblock_user(
    user_id: str,
    ctx: AuthContext = Depends(require_manage_users),
) -> dict:
    target = await db.select_one("users", {"id": user_id}, columns="id,is_blocked")
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await db.update("users", {"id": user_id}, {"is_blocked": False, "block_reason": ""})
    rbac_engine.invalidate(user_id)
    audit_logger.record("rbac.user_unblocked", user_id=user_id, actor_id=ctx.user_id)
    return {"success": True, "message": "User unblocked"}


@router.get("/audit/log")
async def get_audit_log(
    user_id: Optional[str] = Query(None),
    event:   Optional[str] = Query(None),
    limit:   int           = Query(200, ge=1, le=1000),
    ctx: AuthContext = Depends(require_audit_log),
) -> dict:
    entries = audit_logger.query(user_id=user_id, event=event, limit=limit)
    return {"success": True, "entries": entries, "count": len(entries)}


@router.delete("/{user_id}")
async def delete_user(
    user_id: str,
    ctx: AuthContext = Depends(require_admin),
) -> dict:
    if user_id == ctx.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    try:
        await db.delete("user_settings",  {"user_id": user_id})
        await db.delete("refresh_tokens", {"user_id": user_id})
        await db.delete("signals",        {"user_id": user_id})
        await db.delete("user_profiles",  {"id": user_id})
        await db.delete("users",          {"id": user_id})
        rbac_engine.invalidate(user_id)
        audit_logger.record("admin.user.deleted", user_id=user_id, actor_id=ctx.user_id)
        return {"success": True, "message": "User permanently deleted"}
    except Exception as exc:
        logger.error("delete_user error: %s", exc)
        raise HTTPException(status_code=500, detail="Deletion failed")


@router.get("/permissions/matrix")
async def permission_matrix(ctx: AuthContext = Depends(require_admin)) -> dict:
    matrix = {}
    for role in [Role.READONLY, Role.CUSTOMER, Role.SUPPORT, Role.ADMIN, Role.SUPER]:
        matrix[role] = sorted(rbac_engine.get_role_permissions(role))
    return {"success": True, "matrix": matrix}
