"""
سرویس لایسنس (Wrapper)

Wrapper برای LicenseManager با قابلیت‌های اضافی.

نویسنده: MT5 Trading Team
"""

from typing import Dict, Any, Optional

from ..core.logger import get_logger
from ..core.exceptions import LicenseError
from ..license.manager import license_manager, Feature
from .audit_service import audit_service, AuditAction

logger = get_logger("license_service")


class LicenseService:
    """
    سرویس لایسنس

    مسئولیت‌ها:
    - اعتبارسنجی لایسنس
    - بررسی دسترسی‌ها
    - مدیریت دستگاه‌ها
    """

    async def validate(
        self,
        license_key: str,
        device_id: Optional[str] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        اعتبارسنجی لایسنس

        Args:
            license_key: کلید لایسنس
            device_id: شناسه دستگاه
            user_id: شناسه کاربر
            ip_address: آدرس IP

        Returns:
            اطلاعات لایسنس

        Raises:
            LicenseError: اگر نامعتبر باشد
        """
        try:
            result = await license_manager.validate_license(license_key, device_id)

            # ثبت لاگ
            await audit_service.log_license(
                action=AuditAction.LICENSE_VALIDATE,
                license_key=license_key,
                user_id=user_id or result.get("user_id"),
                device_id=device_id,
                success=True,
                ip_address=ip_address
            )

            return {
                "valid": True,
                "license_type": result.get("license_type"),
                "expires_at": result.get("expires_at"),
                "days_remaining": self._calculate_days_remaining(result.get("expires_at")),
                "features": result.get("features", []),
                "devices": {
                    "limit": result.get("devices_limit", 1),
                    "used": result.get("devices_used", 0)
                }
            }

        except Exception as e:
            # ثبت لاگ ناموفق
            await audit_service.log_license(
                action=AuditAction.LICENSE_VALIDATE,
                license_key=license_key,
                user_id=user_id,
                device_id=device_id,
                success=False,
                error_message=str(e),
                ip_address=ip_address
            )
            raise

    async def has_feature(
        self,
        license_key: str,
        feature: str
    ) -> bool:
        """
        بررسی دسترسی به ویژگی

        Args:
            license_key: کلید لایسنس
            feature: نام ویژگی

        Returns:
            True اگر دسترسی باشد
        """
        try:
            feature_enum = Feature(feature)
            return await license_manager.check_feature(license_key, feature_enum)
        except ValueError:
            return False
        except Exception:
            return False

    async def activate_device(
        self,
        license_key: str,
        device_id: str,
        device_name: Optional[str] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        فعال‌سازی دستگاه

        Args:
            license_key: کلید لایسنس
            device_id: شناسه دستگاه
            device_name: نام دستگاه
            user_id: شناسه کاربر
            ip_address: آدرس IP

        Returns:
            نتیجه
        """
        try:
            result = await license_manager.activate_device(
                license_key=license_key,
                device_id=device_id,
                device_name=device_name
            )

            # ثبت لاگ
            await audit_service.log_license(
                action=AuditAction.LICENSE_ACTIVATE,
                license_key=license_key,
                user_id=user_id,
                device_id=device_id,
                success=True,
                ip_address=ip_address
            )

            return {
                "success": True,
                "device_id": device_id,
                "message": "دستگاه با موفقیت فعال شد"
            }

        except Exception as e:
            await audit_service.log_license(
                action=AuditAction.LICENSE_ACTIVATE,
                license_key=license_key,
                user_id=user_id,
                device_id=device_id,
                success=False,
                error_message=str(e),
                ip_address=ip_address
            )
            raise

    async def deactivate_device(
        self,
        license_key: str,
        device_id: str,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        غیرفعال‌سازی دستگاه

        Args:
            license_key: کلید لایسنس
            device_id: شناسه دستگاه
            user_id: شناسه کاربر
            ip_address: آدرس IP

        Returns:
            نتیجه
        """
        result = await license_manager.deactivate_device(license_key, device_id)

        await audit_service.log_license(
            action=AuditAction.LICENSE_ACTIVATE,
            license_key=license_key,
            user_id=user_id,
            device_id=device_id,
            success=True,
            ip_address=ip_address
        )

        return {
            "success": result,
            "message": "دستگاه غیرفعال شد" if result else "دستگاه یافت نشد"
        }

    async def get_user_license(
        self,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        دریافت لایسنس کاربر

        Args:
            user_id: شناسه کاربر

        Returns:
            اطلاعات لایسنس یا None
        """
        return await license_manager.get_user_license(user_id)

    async def get_license_stats(
        self,
        license_key: str
    ) -> Dict[str, Any]:
        """
        آمار لایسنس

        Args:
            license_key: کلید لایسنس

        Returns:
            آمار
        """
        return await license_manager.get_license_stats(license_key)

    def _calculate_days_remaining(self, expires_at: Optional[str]) -> int:
        """محاسبه روزهای باقی‌مانده"""
        if not expires_at:
            return 0

        from datetime import datetime
        try:
            expiry = datetime.fromisoformat(expires_at)
            remaining = (expiry - datetime.utcnow()).days
            return max(0, remaining)
        except Exception:
            return 0


# نمونه گلوبال
license_service = LicenseService()
