"""
سیستم لایسنس

مدیریت لایسنس‌ها و دسترسی‌ها با قابلیت‌های:
- اعتبارسنجی لایسنس
- مدیریت سطوح دسترسی
- محدودیت ویژگی‌ها
- تاریخ انقضا
- دستگاه‌های مجاز

نویسنده: MT5 Trading Team
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import hashlib
import secrets

from ..core.logger import get_logger
from ..core.exceptions import LicenseError, LicenseExpiredError, FeatureNotLicensedError
from ..database import db

logger = get_logger("license")


class LicenseType(str, Enum):
    """انواع لایسنس"""
    TRIAL = "trial"           # آزمایشی (7 روز)
    BASIC = "basic"           # پایه (1 ماه)
    PRO = "pro"               # حرفه‌ای (3 ماه)
    ENTERPRISE = "enterprise" # سازمانی (1 سال)
    LIFETIME = "lifetime"     # مادام‌العمر


class PermissionLevel(str, Enum):
    """سطوح دسترسی"""
    READ_ONLY = "read_only"           # فقط مشاهده
    SIGNALS_ONLY = "signals_only"    # فقط سیگنال
    MANUAL_TRADE = "manual_trade"    # معامله دستی
    AUTO_TRADE = "auto_trade"         # معامله خودکار
    FULL_ACCESS = "full_access"       # دسترسی کامل
    ADMIN = "admin"                   # مدیر


class Feature(str, Enum):
    """ویژگی‌های سیستم"""
    # تحلیل
    SMC_ANALYSIS = "smc_analysis"
    PRICE_ACTION = "price_action"
    MULTI_TIMEFRAME = "multi_timeframe"

    # معاملات
    MANUAL_TRADING = "manual_trading"
    AUTO_TRADING = "auto_trading"

    # ابزارها
    TELEGRAM_BOT = "telegram_bot"
    DASHBOARD = "dashboard"
    CHART_DRAWING = "chart_drawing"

    # گزارش‌ها
    DAILY_REPORTS = "daily_reports"
    ADVANCED_REPORTS = "advanced_reports"

    # تنظیمات
    CUSTOM_STRATEGIES = "custom_strategies"
    API_ACCESS = "api_access"


# ویژگی‌های هر نوع لایسنس
LICENSE_FEATURES: Dict[LicenseType, List[Feature]] = {
    LicenseType.TRIAL: [
        Feature.SMC_ANALYSIS,
        Feature.PRICE_ACTION,
        Feature.SIGNALS_ONLY,
        Feature.DAILY_REPORTS,
    ],
    LicenseType.BASIC: [
        Feature.SMC_ANALYSIS,
        Feature.PRICE_ACTION,
        Feature.MULTI_TIMEFRAME,
        Feature.MANUAL_TRADING,
        Feature.TELEGRAM_BOT,
        Feature.DASHBOARD,
        Feature.DAILY_REPORTS,
    ],
    LicenseType.PRO: [
        Feature.SMC_ANALYSIS,
        Feature.PRICE_ACTION,
        Feature.MULTI_TIMEFRAME,
        Feature.MANUAL_TRADING,
        Feature.AUTO_TRADING,
        Feature.TELEGRAM_BOT,
        Feature.DASHBOARD,
        Feature.CHART_DRAWING,
        Feature.DAILY_REPORTS,
        Feature.ADVANCED_REPORTS,
        Feature.API_ACCESS,
    ],
    LicenseType.ENTERPRISE: [
        Feature.SMC_ANALYSIS,
        Feature.PRICE_ACTION,
        Feature.MULTI_TIMEFRAME,
        Feature.MANUAL_TRADING,
        Feature.AUTO_TRADING,
        Feature.TELEGRAM_BOT,
        Feature.DASHBOARD,
        Feature.CHART_DRAWING,
        Feature.DAILY_REPORTS,
        Feature.ADVANCED_REPORTS,
        Feature.CUSTOM_STRATEGIES,
        Feature.API_ACCESS,
    ],
    LicenseType.LIFETIME: [f for f in Feature],
}

# مدت اعتبار لایسنس‌ها (روز)
LICENSE_DURATION: Dict[LicenseType, int] = {
    LicenseType.TRIAL: 7,
    LicenseType.BASIC: 30,
    LicenseType.PRO: 90,
    LicenseType.ENTERPRISE: 365,
    LicenseType.LIFETIME: 36500,  # 100 سال
}


class LicenseManager:
    """
    مدیر لایسنس

    مسئولیت‌ها:
    - ایجاد و مدیریت لایسنس
    - اعتبارسنجی لایسنس
    - بررسی دسترسی به ویژگی‌ها
    - مدیریت دستگاه‌های مجاز
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}

    async def create_license(
        self,
        user_id: str,
        license_type: LicenseType,
        devices_limit: int = 1,
        created_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ایجاد لایسنس جدید

        Args:
            user_id: شناسه کاربر
            license_type: نوع لایسنس
            devices_limit: حداکثر دستگاه مجاز
            created_by: ایجادکننده (برای ادمین)

        Returns:
            اطلاعات لایسنس ایجاد شده
        """
        # تولید کلید لایسنس
        license_key = self._generate_license_key()

        # محاسبه تاریخ انقضا
        duration = LICENSE_DURATION[license_type]
        expires_at = datetime.utcnow() + timedelta(days=duration)

        # ایجاد رکورد لایسنس
        license_data = {
            "license_key": license_key,
            "user_id": user_id,
            "license_type": license_type.value,
            "status": "active",
            "devices_limit": devices_limit,
            "devices_used": 0,
            "expires_at": expires_at.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "created_by": created_by,
            "features": [f.value for f in LICENSE_FEATURES[license_type]]
        }

        # ذخیره در دیتابیس
        result = await db.insert("licenses", license_data)

        logger.info(f"لایسنس جدید ایجاد شد: {license_key} برای کاربر {user_id}")

        return result

    async def validate_license(
        self,
        license_key: str,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        اعتبارسنجی لایسنس

        Args:
            license_key: کلید لایسنس
            device_id: شناسه دستگاه

        Returns:
            اطلاعات لایسنس

        Raises:
            LicenseError: اگر لایسنس نامعتبر باشد
            LicenseExpiredError: اگر لایسنس منقضی شده باشد
        """
        # دریافت از کش یا دیتابیس
        if license_key in self._cache:
            cached = self._cache[license_key]
            # بررسی کش (5 دقیقه)
            if (datetime.utcnow() - datetime.fromisoformat(cached["_cached_at"])).total_seconds() < 300:
                return cached

        # دریافت از دیتابیس
        license_data = await db.select_one("licenses", {"license_key": license_key})

        if not license_data:
            raise LicenseError("لایسنس یافت نشد")

        # بررسی وضعیت
        if license_data["status"] != "active":
            raise LicenseError(f"لایسنس {license_data['status']} است")

        # بررسی انقضا
        expires_at = datetime.fromisoformat(license_data["expires_at"])
        if datetime.utcnow() > expires_at:
            # به‌روزرسانی وضعیت
            await db.update("licenses", {"license_key": license_key}, {"status": "expired"})
            raise LicenseExpiredError("لایسنس منقضی شده است")

        # بررسی دستگاه
        if device_id:
            await self._check_device(license_data, device_id)

        # کش کردن
        license_data["_cached_at"] = datetime.utcnow().isoformat()
        self._cache[license_key] = license_data

        return license_data

    async def check_feature(
        self,
        license_key: str,
        feature: Feature
    ) -> bool:
        """
        بررسی دسترسی به ویژگی

        Args:
            license_key: کلید لایسنس
            feature: ویژگی مورد نظر

        Returns:
            True اگر دسترسی وجود داشته باشد

        Raises:
            FeatureNotLicensedError: اگر دسترسی وجود نداشته باشد
        """
        license_data = await self.validate_license(license_key)

        features = license_data.get("features", [])

        if feature.value not in features:
            raise FeatureNotLicensedError(f"دسترسی به {feature.value} مجاز نیست")

        return True

    async def get_user_license(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        دریافت لایسنس فعال کاربر

        Args:
            user_id: شناسه کاربر

        Returns:
            اطلاعات لایسنس یا None
        """
        licenses = await db.select_many(
            "licenses",
            filters={"user_id": user_id, "status": "active"},
            order_by="created_at",
            order_desc=True,
            limit=1
        )

        if not licenses:
            return None

        return licenses[0]

    async def activate_device(
        self,
        license_key: str,
        device_id: str,
        device_name: Optional[str] = None
    ) -> bool:
        """
        فعال‌سازی دستگاه جدید

        Args:
            license_key: کلید لایسنس
            device_id: شناسه دستگاه
            device_name: نام دستگاه

        Returns:
            True اگر موفق باشد

        Raises:
            LicenseError: اگر حداکثر دستگاه‌ها استفاده شده باشد
        """
        license_data = await self.validate_license(license_key)

        # بررسی تعداد دستگاه‌ها
        devices_used = license_data.get("devices_used", 0)
        devices_limit = license_data.get("devices_limit", 1)

        # بررسی دستگاه قبلاً ثبت شده
        existing = await db.select_one("license_devices", {
            "license_key": license_key,
            "device_id": device_id
        })

        if existing:
            # به‌روزرسانی آخرین استفاده
            await db.update(
                "license_devices",
                {"id": existing["id"]},
                {"last_used_at": datetime.utcnow().isoformat()}
            )
            return True

        # بررسی محدودیت
        if devices_used >= devices_limit:
            raise LicenseError(
                f"حداکثر {devices_limit} دستگاه مجاز است. "
                "لطفاً یک دستگاه را غیرفعال کنید."
            )

        # ثبت دستگاه جدید
        await db.insert("license_devices", {
            "license_key": license_key,
            "device_id": device_id,
            "device_name": device_name or f"Device-{device_id[:8]}",
            "activated_at": datetime.utcnow().isoformat(),
            "last_used_at": datetime.utcnow().isoformat()
        })

        # به‌روزرسانی تعداد
        await db.update(
            "licenses",
            {"license_key": license_key},
            {"devices_used": devices_used + 1}
        )

        logger.info(f"دستگاه جدید فعال شد: {device_id} برای لایسنس {license_key}")

        return True

    async def deactivate_device(
        self,
        license_key: str,
        device_id: str
    ) -> bool:
        """
        غیرفعال‌سازی دستگاه

        Args:
            license_key: کلید لایسنس
            device_id: شناسه دستگاه

        Returns:
            True اگر موفق باشد
        """
        # حذف دستگاه
        deleted = await db.delete("license_devices", {
            "license_key": license_key,
            "device_id": device_id
        })

        if deleted:
            # کاهش تعداد
            license_data = await db.select_one("licenses", {"license_key": license_key})
            if license_data:
                await db.update(
                    "licenses",
                    {"license_key": license_key},
                    {"devices_used": max(0, license_data.get("devices_used", 1) - 1)}
                )

        logger.info(f"دستگاه غیرفعال شد: {device_id}")

        return bool(deleted)

    async def revoke_license(self, license_key: str) -> bool:
        """
        ابطال لایسنس

        Args:
            license_key: کلید لایسنس

        Returns:
            True اگر موفق باشد
        """
        result = await db.update(
            "licenses",
            {"license_key": license_key},
            {"status": "revoked", "revoked_at": datetime.utcnow().isoformat()}
        )

        # حذف از کش
        if license_key in self._cache:
            del self._cache[license_key]

        logger.warning(f"لایسنس ابطال شد: {license_key}")

        return bool(result)

    async def extend_license(
        self,
        license_key: str,
        days: int
    ) -> Dict[str, Any]:
        """
        تمدید لایسنس

        Args:
            license_key: کلید لایسنس
            days: تعداد روز تمدید

        Returns:
            اطلاعات لایسنس به‌روز شده
        """
        license_data = await db.select_one("licenses", {"license_key": license_key})

        if not license_data:
            raise LicenseError("لایسنس یافت نشد")

        # محاسبه تاریخ انقضای جدید
        current_expiry = datetime.fromisoformat(license_data["expires_at"])
        if current_expiry > datetime.utcnow():
            new_expiry = current_expiry + timedelta(days=days)
        else:
            new_expiry = datetime.utcnow() + timedelta(days=days)

        # به‌روزرسانی
        result = await db.update(
            "licenses",
            {"license_key": license_key},
            {
                "expires_at": new_expiry.isoformat(),
                "status": "active"
            }
        )

        # حذف از کش
        if license_key in self._cache:
            del self._cache[license_key]

        logger.info(f"لایسنس تمدید شد: {license_key} به مدت {days} روز")

        return result[0] if result else license_data

    async def get_license_stats(self, license_key: str) -> Dict[str, Any]:
        """
        دریافت آمار لایسنس

        Args:
            license_key: کلید لایسنس

        Returns:
            آمار لایسنس
        """
        license_data = await self.validate_license(license_key)

        # دریافت دستگاه‌ها
        devices = await db.select_many(
            "license_devices",
            filters={"license_key": license_key}
        )

        # محاسبه روزهای باقی‌مانده
        expires_at = datetime.fromisoformat(license_data["expires_at"])
        days_remaining = (expires_at - datetime.utcnow()).days

        return {
            "license_key": license_key,
            "license_type": license_data["license_type"],
            "status": license_data["status"],
            "days_remaining": max(0, days_remaining),
            "devices": {
                "limit": license_data["devices_limit"],
                "used": license_data["devices_used"],
                "list": devices
            },
            "features": license_data["features"]
        }

    def _generate_license_key(self) -> str:
        """
        تولید کلید لایسنس

        Returns:
            کلید لایسنس یکتا
        """
        # فرمت: MT5-XXXX-XXXX-XXXX-XXXX
        random_bytes = secrets.token_hex(8)
        parts = [
            random_bytes[i:i+4].upper()
            for i in range(0, 16, 4)
        ]
        return f"MT5-{parts[0]}-{parts[1]}-{parts[2]}-{parts[3]}"

    async def _check_device(
        self,
        license_data: Dict[str, Any],
        device_id: str
    ) -> bool:
        """
        بررسی دستگاه

        Args:
            license_data: اطلاعات لایسنس
            device_id: شناسه دستگاه

        Returns:
            True اگر دستگاه مجاز باشد

        Raises:
            LicenseError: اگر دستگاه مجاز نباشد
        """
        # بررسی دستگاه ثبت شده
        device = await db.select_one("license_devices", {
            "license_key": license_data["license_key"],
            "device_id": device_id
        })

        if device:
            # به‌روزرسانی آخرین استفاده
            await db.update(
                "license_devices",
                {"id": device["id"]},
                {"last_used_at": datetime.utcnow().isoformat()}
            )
            return True

        # دستگاه جدید - بررسی محدودیت
        devices_used = license_data.get("devices_used", 0)
        devices_limit = license_data.get("devices_limit", 1)

        if devices_used >= devices_limit:
            raise LicenseError(
                f"این دستگاه مجاز نیست. "
                f"حداکثر {devices_limit} دستگاه می‌توانید استفاده کنید."
            )

        return True


# نمونه گلوبال
license_manager = LicenseManager()
