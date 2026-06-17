"""
روت‌های لایسنس

Endpointهای مربوط به اعتبارسنجی و مدیریت لایسنس.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from ...core.logger import get_logger
from ...core.exceptions import LicenseError, LicenseExpiredError
from ...services.license_service import license_service
from .auth import get_current_user

logger = get_logger("api.license")
router = APIRouter()


# =====================================================
# مدل‌های Pydantic
# =====================================================

class LicenseValidateRequest(BaseModel):
    """درخواست اعتبارسنجی لایسنس"""
    license_key: str = Field(..., description="کلید لایسنس")
    device_id: Optional[str] = Field(default=None, description="شناسه دستگاه")


class DeviceActivateRequest(BaseModel):
    """درخواست فعال‌سازی دستگاه"""
    license_key: str = Field(..., description="کلید لایسنس")
    device_id: str = Field(..., description="شناسه دستگاه")
    device_name: Optional[str] = Field(default=None, description="نام دستگاه")


class LicenseResponse(BaseModel):
    """پاسخ لایسنس"""
    success: bool
    data: Dict[str, Any]
    message: Optional[str] = None


# =====================================================
# Public Endpoints (بدون احراز هویت)
# =====================================================

@router.post("/validate", response_model=LicenseResponse)
async def validate_license(
    request: Request,
    data: LicenseValidateRequest
):
    """
    اعتبارسنجی لایسنس

    این endpoint توسط MT5 EA یا Telegram Bot برای بررسی اعتبار لایسنس استفاده می‌شود.
    نیازی به توکن احراز هویت ندارد.

    خروجی:
    - valid: وضعیت اعتبار
    - license_type: نوع لایسنس
    - expires_at: تاریخ انقضا
    - days_remaining: روزهای باقی‌مانده
    - features: لیست ویژگی‌های مجاز
    """
    logger.info(f"درخواست اعتبارسنجی لایسنس: {data.license_key[:12]}****")

    ip_address = request.client.host if request.client else None

    try:
        result = await license_service.validate(
            license_key=data.license_key,
            device_id=data.device_id,
            ip_address=ip_address
        )

        return {
            "success": True,
            "data": result,
            "message": "لایسنس معتبر است"
        }

    except LicenseExpiredError as e:
        return {
            "success": False,
            "data": {"valid": False, "reason": "expired"},
            "message": str(e)
        }
    except LicenseError as e:
        return {
            "success": False,
            "data": {"valid": False, "reason": "invalid"},
            "message": str(e)
        }


@router.post("/activate", response_model=LicenseResponse)
async def activate_device(
    request: Request,
    data: DeviceActivateRequest
):
    """
    فعال‌سازی دستگاه

    ثبت دستگاه جدید برای لایسنس.
    """
    logger.info(f"درخواست فعال‌سازی دستگاه: {data.device_id}")

    ip_address = request.client.host if request.client else None

    try:
        result = await license_service.activate_device(
            license_key=data.license_key,
            device_id=data.device_id,
            device_name=data.device_name,
            ip_address=ip_address
        )

        return {
            "success": True,
            "data": result,
            "message": "دستگاه با موفقیت فعال شد"
        }

    except LicenseError as e:
        return {
            "success": False,
            "data": {},
            "message": str(e)
        }


@router.post("/deactivate", response_model=LicenseResponse)
async def deactivate_device(
    request: Request,
    data: DeviceActivateRequest
):
    """
    غیرفعال‌سازی دستگاه

    حذف دستگاه از لیست دستگاه‌های مجاز.
    """
    logger.info(f"درخواست غیرفعال‌سازی دستگاه: {data.device_id}")

    ip_address = request.client.host if request.client else None

    result = await license_service.deactivate_device(
        license_key=data.license_key,
        device_id=data.device_id,
        ip_address=ip_address
    )

    return {
        "success": result["success"],
        "data": {},
        "message": result["message"]
    }


@router.post("/feature-check")
async def check_feature_access(
    license_key: str,
    feature: str
):
    """
    بررسی دسترسی به ویژگی

    بررسی اینکه آیا لایسنس به ویژگی خاصی دسترسی دارد.
    """
    has_access = await license_service.has_feature(license_key, feature)

    return {
        "success": True,
        "data": {
            "feature": feature,
            "has_access": has_access
        }
    }


# =====================================================
# Protected Endpoints (با احراز هویت)
# =====================================================

@router.get("/my")
async def get_my_license(
    user: dict = Depends(get_current_user)
):
    """
    دریافت لایسنس کاربر جاری

    اطلاعات لایسنس فعال کاربر را برمی‌گرداند.
    """
    license_data = await license_service.get_user_license(user.get("id"))

    if not license_data:
        return {
            "success": True,
            "data": None,
            "message": "لایسنس فعالی یافت نشد"
        }

    # حذف اطلاعات حساس
    safe_data = {
        "license_key": license_data.get("license_key", "")[:12] + "****",
        "license_type": license_data.get("license_type"),
        "status": license_data.get("status"),
        "expires_at": license_data.get("expires_at"),
        "features": license_data.get("features", []),
        "devices": {
            "limit": license_data.get("devices_limit", 1),
            "used": license_data.get("devices_used", 0)
        }
    }

    return {
        "success": True,
        "data": safe_data
    }


@router.get("/stats")
async def get_license_stats(
    user: dict = Depends(get_current_user)
):
    """
    آمار لایسنس
    """
    license_data = await license_service.get_user_license(user.get("id"))

    if not license_data:
        raise HTTPException(status_code=404, detail="لایسنس یافت نشد")

    stats = await license_service.get_license_stats(
        license_key=license_data.get("license_key")
    )

    # پاک کردن کلید کامل
    stats["license_key"] = stats.get("license_key", "")[:12] + "****"

    return {
        "success": True,
        "data": stats
    }
