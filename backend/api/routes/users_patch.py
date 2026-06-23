"""backend/api/routes/users_patch.py -- Phase U
U-11: GET /users/profile returns password_hash (data leak) - FIXED
U-12: PUT /users/profile no field sanitization - FIXED
U-13: GET /users/settings returns empty {} - FIXED
U-14: PUT /users/settings accepts arbitrary JSON - FIXED
U-15: DELETE /users/account missing - GDPR violation - FIXED
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from backend.core.deps import get_current_user, get_db
from backend.core.logger import get_logger
logger = get_logger("api.users_patch")
router = APIRouter(tags=["Users"])

_PROFILE_SAFE_FIELDS = frozenset({
    "id", "email", "full_name", "avatar_url",
    "created_at", "updated_at", "telegram_id",
})
_PROFILE_EDITABLE_FIELDS = frozenset({"full_name", "avatar_url", "telegram_id"})
_SETTINGS_ALLOWED_KEYS = frozenset({
    "language", "timezone", "notifications_enabled",
    "telegram_alerts", "email_alerts",
    "default_lot_size", "default_risk_pct",
    "theme", "dashboard_layout",
})


def _strip_sensitive(row: Dict[str, Any]) -> Dict[str, Any]:
    """U-11: remove password_hash, role, is_admin."""
    return {k: v for k, v in row.items() if k in _PROFILE_SAFE_FIELDS}


class UpdateProfileRequest(BaseModel):
    full_name:   Optional[str] = Field(None, min_length=1, max_length=120)
    avatar_url:  Optional[str] = Field(None, max_length=500)
    telegram_id: Optional[str] = Field(None, max_length=50)

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class UserSettingsRequest(BaseModel):
    """U-14: typed schema - only allowed keys."""
    language:              Optional[str]   = Field(None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    timezone:              Optional[str]   = Field(None, max_length=50)
    notifications_enabled: Optional[bool]  = None
    telegram_alerts:       Optional[bool]  = None
    email_alerts:          Optional[bool]  = None
    default_lot_size:      Optional[float] = Field(None, ge=0.01, le=100.0)
    default_risk_pct:      Optional[float] = Field(None, ge=0.1,  le=10.0)
    theme:                 Optional[str]   = Field(None, pattern=r"^(light|dark|system)$")
    dashboard_layout:      Optional[str]   = Field(None, max_length=20)


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user), db: Any = Depends(get_db)) -> Dict[str, Any]:
    """U-11 FIX: strip sensitive fields."""
    row = await db.select_one("users", {"id": user["sub"]})
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _strip_sensitive(row)


@router.put("/profile")
async def update_profile(body: UpdateProfileRequest, user: dict = Depends(get_current_user), db: Any = Depends(get_db)) -> Dict[str, Any]:
    """U-12 FIX: only editable fields allowed."""
    updates = {k: getattr(body, k) for k in _PROFILE_EDITABLE_FIELDS if getattr(body, k, None) is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.update("users", {"id": user["sub"]}, updates)
    if not result:
        raise HTTPException(status_code=500, detail="Update failed")
    row = result[0] if isinstance(result, list) else result
    return _strip_sensitive(row)


@router.get("/settings")
async def get_settings_endpoint(user: dict = Depends(get_current_user), db: Any = Depends(get_db)) -> Dict[str, Any]:
    """U-13 FIX: reads from user_settings table."""
    row = await db.select_one("user_settings", {"user_id": user["sub"]})
    if not row:
        return {k: None for k in _SETTINGS_ALLOWED_KEYS}
    return {k: row.get(k) for k in _SETTINGS_ALLOWED_KEYS}


@router.put("/settings")
async def update_settings_endpoint(body: UserSettingsRequest, user: dict = Depends(get_current_user), db: Any = Depends(get_db)) -> Dict[str, Any]:
    """U-14 FIX: typed schema only."""
    updates = {k: v for k, v in body.model_dump(exclude_none=True).items() if k in _SETTINGS_ALLOWED_KEYS}
    if not updates:
        raise HTTPException(status_code=400, detail="No valid settings")
    updates["user_id"]    = user["sub"]
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.upsert("user_settings", updates)
    return {k: updates.get(k) for k in _SETTINGS_ALLOWED_KEYS}


@router.delete("/account")
async def delete_account(user: dict = Depends(get_current_user), db: Any = Depends(get_db)) -> Dict[str, Any]:
    """U-15 FIX: GDPR Article 17 - right to erasure."""
    uid = user["sub"]
    now = datetime.now(timezone.utc).isoformat()
    try:
        await db.update("users", {"id": uid}, {
            "email": f"deleted_{uid[:8]}@deleted.invalid",
            "full_name": "Deleted User",
            "avatar_url": None, "telegram_id": None,
            "password_hash": "$deleted$",
            "is_deleted": True, "deleted_at": now, "updated_at": now,
        })
        await db.delete("refresh_tokens", {"user_id": uid})
        logger.info("[GDPR] account deleted user=%s", uid[:8])
        return {"success": True, "message": "Account deleted"}
    except Exception as exc:
        logger.error("[GDPR] delete failed user=%s: %s", uid[:8], exc)
        raise HTTPException(status_code=500, detail="Account deletion failed")
