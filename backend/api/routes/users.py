"""
روت‌های کاربران

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from ...core.logger import get_logger
from ...database import db
from .auth import get_current_user

logger = get_logger("api.users")
router = APIRouter()


class UpdateProfileRequest(BaseModel):
    """درخواست به‌روزرسانی پروفایل"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None


class UpdateSettingsRequest(BaseModel):
    """درخواست به‌روزرسانی تنظیمات"""
    default_symbol: Optional[str] = None
    default_lot: Optional[float] = None
    risk_per_trade: Optional[float] = None
    max_daily_trades: Optional[int] = None
    min_entry_score: Optional[float] = None
    telegram_notifications: Optional[bool] = None


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """دریافت پروفایل کاربر"""
    return {
        "success": True,
        "data": user
    }


@router.patch("/profile")
async def update_profile(
    request: UpdateSettingsRequest,
    user: dict = Depends(get_current_user)
):
    """به‌روزرسانی پروفایل"""
    update_data = request.dict(exclude_unset=True)

    if not update_data:
        return {"success": True, "message": "هیچ تغییری اعمال نشد"}

    updated = await db.update(
        "user_profiles",
        {"id": user["id"]},
        update_data
    )

    logger.info(f"پروفایل به‌روزرسانی شد: {user['id']}")

    return {
        "success": True,
        "message": "پروفایل به‌روزرسانی شد",
        "data": updated[0] if updated else None
    }


@router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    """دریافت تنظیمات کاربر"""
    settings_data = await db.select_one("user_settings", {"user_id": user["id"]})

    if not settings_data:
        # ایجاد تنظیمات پیش‌فرض
        settings_data = await db.insert("user_settings", {"user_id": user["id"]})

    return {
        "success": True,
        "data": settings_data
    }


@router.put("/settings")
async def update_settings(
    request: UpdateSettingsRequest,
    user: dict = Depends(get_current_user)
):
    """به‌روزرسانی تنظیمات"""
    update_data = request.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow().isoformat()

    updated = await db.update(
        "user_settings",
        {"user_id": user["id"]},
        update_data
    )

    logger.info(f"تنظیمات به‌روزرسانی شد: {user['id']}")

    return {
        "success": True,
        "message": "تنظیمات ذخیره شد",
        "data": updated[0] if updated else None
    }
