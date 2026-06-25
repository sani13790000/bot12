"""
backend/api/routes/users.py

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

from backend.core.deps import get_current_user
from backend.core.logger import get_logger
from backend.database import db

logger = get_logger("api.users")
router = APIRouter()

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
    """U-11: remove password_hash and all non-whitelisted fields."""
    return {k: v for k, v in row.items() if k in _PROFILE_SAFE_FIELDS}


class UpdateProfileRequest(BaseModel):
    full_name:   Optional[str] = Field(None, min_length=1, max_length=120)
    avatar_url:  Optional[str] = Field(None, max_length=500)
    telegram_id: Optional[str] = Field(None, max_length=50)

    @field_validator("full_name")
    @classmethod
    def _strip(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v


class UpdateSettingsRequest(BaseModel):
    language:              Optional[str]   = None
    timezone:              Optional[str]   = None
    notifications_enabled: Optional[bool]  = None
    telegram_alerts:       Optional[bool]  = None
    email_alerts:          Optional[bool]  = None
    default_lot_size:      Optional[float] = Field(None, gt=0.0, le=100.0)
    default_risk_pct:      Optional[float] = Field(None, gt=0.0, le=10.0)
    theme:                 Optional[str]   = None
    dashboard_layout:      Optional[str]   = None


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """U-11: strip password_hash and sensitive fields before returning."""
    return {"success": True, "data": _strip_sensitive(user)}


@router.patch("/profile")
async def update_profile(
    request: UpdateProfileRequest,
    user: dict = Depends(get_current_user),
):
    """U-12: only whitelisted editable fields accepted."""
    update_data = {
        k: v for k, v in request.model_dump(exclude_unset=True).items()
        if k in _PROFILE_EDITABLE_FIELDS and v is not None
    }
    if not update_data:
        return {"success": True, "message": "هیچ تغییری اعمال نشد"}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = await db.update("user_profiles", {"id": user.get("id") or user.get("sub")}, update_data)
    logger.info("Profile updated: %s", user.get("id"))
    return {
        "success": True,
        "message": "پروفایل به‌روزرسانی شد",
        "data": _strip_sensitive(updated[0]) if updated else None,
    }


@router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    """U-13: return actual stored settings, not empty {}."""
    uid = user.get("id") or user.get("sub")
    settings_data = await db.select_one("user_settings", {"user_id": uid})
    if not settings_data:
        settings_data = await db.insert(
            "user_settings",
            {"user_id": uid, "created_at": datetime.now(timezone.utc).isoformat()},
        )
    safe = {k: v for k, v in (settings_data or {}).items() if k in _SETTINGS_ALLOWED_KEYS}
    return {"success": True, "data": safe}


@router.put("/settings")
async def update_settings(
    request: UpdateSettingsRequest,
    user: dict = Depends(get_current_user),
):
    """U-14: only whitelisted keys stored."""
    uid = user.get("id") or user.get("sub")
    update_data = {
        k: v for k, v in request.model_dump(exclude_unset=True).items()
        if k in _SETTINGS_ALLOWED_KEYS and v is not None
    }
    if not update_data:
        return {"success": True, "message": "هیچ تغییری اعمال نشد"}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = await db.update("user_settings", {"user_id": uid}, update_data)
    logger.info("Settings updated: %s", uid)
    return {"success": True, "message": "تنظیمات ذخیره شد", "data": updated[0] if updated else None}


@router.delete("/account")
async def delete_account(user: dict = Depends(get_current_user)):
    """U-15: GDPR-compliant account deletion."""
    uid = user.get("id") or user.get("sub")
    if not uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user")
    try:
        await db.delete("user_settings", {"user_id": uid})
        await db.delete("signals",       {"user_id": uid})
        await db.delete("user_profiles", {"id": uid})
        logger.info("Account deleted (GDPR): %s", uid)
        return {"success": True, "message": "حساب کاربری حذف شد"}
    except Exception as exc:
        logger.error("Account deletion failed for %s: %s", uid, exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Deletion failed")
