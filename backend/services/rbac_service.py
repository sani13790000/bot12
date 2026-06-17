"""
سرویس نقش‌ها و دسترسی‌ها

مدیریت نقش‌های کاربری از دیتابیس.

نویسنده: MT5 Trading Team
"""

from datetime import datetime
from typing import Dict, Any, Optional
from functools import lru_cache

from ..core.logger import get_logger
from ..core.exceptions import DatabaseError
from ..database import db
from ..telegram.rbac import (
    UserRole, Permission, has_permission,
    get_role_level, get_min_role_for_permission,
    get_permission_denied_message
)

logger = get_logger("rbac_service")


class RBACService:
    """
    سرویس مدیریت نقش‌ها

    مسئولیت‌ها:
    - دریافت و ذخیره نقش کاربر
    - بررسی دسترسی‌ها
    - ارتباط با لایسنس
    """

    def __init__(self):
        self._cache: Dict[int, Dict[str, Any]] = {}

    async def get_user_role(
        self,
        telegram_user_id: int
    ) -> Optional[UserRole]:
        """
        دریافت نقش کاربر از دیتابیس

        Args:
            telegram_user_id: شناسه تلگرام کاربر

        Returns:
            نقش کاربری یا None
        """
        # بررسی کش
        cached = self._get_cached(telegram_user_id)
        if cached:
            return UserRole(cached.get("role", "user"))

        try:
            # جستجو در user_profiles با telegram_id
            user = await db.select_one(
                "user_profiles",
                {"telegram_id": telegram_user_id},
                use_admin=True
            )

            if not user:
                logger.debug(f"کاربر با telegram_id {telegram_user_id} یافت نشد")
                return None

            role_str = user.get("role", "user")

            # کش کردن
            self._set_cache(telegram_user_id, {
                "role": role_str,
                "user_id": user.get("id"),
                "email": user.get("email"),
                "status": user.get("status")
            })

            return UserRole(role_str)

        except Exception as e:
            logger.error(f"خطا در دریافت نقش کاربر: {e}")
            return None

    async def get_user_by_telegram_id(
        self,
        telegram_user_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        دریافت اطلاعات کامل کاربر با telegram_id

        Args:
            telegram_user_id: شناسه تلگرام

        Returns:
            اطلاعات کاربر
        """
        cached = self._get_cached(telegram_user_id)
        if cached:
            return cached

        try:
            user = await db.select_one(
                "user_profiles",
                {"telegram_id": telegram_user_id},
                use_admin=True
            )

            if user:
                self._set_cache(telegram_user_id, user)

            return user

        except Exception as e:
            logger.error(f"خطا در دریافت کاربر: {e}")
            return None

    async def check_permission(
        self,
        telegram_user_id: int,
        permission: Permission
    ) -> Dict[str, Any]:
        """
        بررسی دسترسی کاربر

        Args:
            telegram_user_id: شناسه تلگرام
            permission: دسترسی مورد نظر

        Returns:
            نتیجه بررسی
        """
        # دریافت کاربر
        user = await self.get_user_by_telegram_id(telegram_user_id)

        if not user:
            return {
                "allowed": False,
                "reason": "not_registered",
                "message": get_permission_denied_message("not_registered")
            }

        # بررسی وضعیت
        if user.get("status") != "active":
            return {
                "allowed": False,
                "reason": "account_inactive",
                "message": "🚫 حساب شما غیرفعال است."
            }

        # دریافت نقش
        role = UserRole(user.get("role", "user"))

        # بررسی دسترسی
        if not has_permission(role, permission):
            required = get_min_role_for_permission(permission)
            return {
                "allowed": False,
                "reason": "no_permission",
                "role": role.value,
                "required_role": required.value if required else "unknown",
                "message": get_permission_denied_message(
                    "no_permission",
                    role.value,
                    required.value if required else "unknown"
                )
            }

        # بررسی لایسنس برای دسترسی‌های حساس
        if permission in [
            Permission.CLOSE_ALL_TRADES,
            Permission.CLOSE_BUY_TRADES,
            Permission.CLOSE_SELL_TRADES,
            Permission.START_BOT,
            Permission.STOP_BOT,
        ]:
            license_check = await self._check_license(user.get("id"))
            if not license_check["valid"]:
                return license_check

        return {
            "allowed": True,
            "role": role,
            "user_id": user.get("id")
        }

    async def check_command_permission(
        self,
        telegram_user_id: int,
        command: str
    ) -> Dict[str, Any]:
        """
        بررسی دسترسی به یک command

        Args:
            telegram_user_id: شناسه تلگرام
            command: دستور

        Returns:
            نتیجه بررسی
        """
        # استخراج دستور اصلی
        cmd = command.split()[0] if " " in command else command
        cmd = cmd.split("@")[0] if "@" in cmd else cmd

        # دریافت دسترسی مورد نیاز
        from ..telegram.rbac import COMMAND_PERMISSIONS

        permission = COMMAND_PERMISSIONS.get(cmd)
        if not permission:
            # command بدون محدودیت
            return {"allowed": True}

        return await self.check_permission(telegram_user_id, permission)

    async def set_user_role(
        self,
        telegram_user_id: int,
        new_role: UserRole,
        admin_id: int
    ) -> bool:
        """
        تنظیم نقش کاربر (نیاز به admin)

        Args:
            telegram_user_id: شناسه تلگرام کاربر
            new_role: نقش جدید
            admin_id: شناسه ادمین

        Returns:
            True اگر موفق بود
        """
        # بررسی دسترسی admin
        admin_role = await self.get_user_role(admin_id)
        if not admin_role or admin_role not in [UserRole.ADMIN, UserRole.SUPER_ADMIN]:
            logger.warning(f"تلاش غیرمجاز برای تغییر نقش توسط {admin_id}")
            return False

        # فقط super_admin می‌تواند admin بسازد
        if new_role == UserRole.ADMIN and admin_role != UserRole.SUPER_ADMIN:
            return False

        try:
            user = await self.get_user_by_telegram_id(telegram_user_id)
            if not user:
                return False

            await db.update(
                "user_profiles",
                {"id": user.get("id")},
                {"role": new_role.value, "updated_at": datetime.utcnow().isoformat()},
                use_admin=True
            )

            # پاک کردن کش
            self._clear_cache(telegram_user_id)

            logger.info(f"نقش کاربر {telegram_user_id} به {new_role.value} تغییر کرد توسط {admin_id}")
            return True

        except Exception as e:
            logger.error(f"خطا در تغییر نقش: {e}")
            return False

    async def register_telegram_user(
        self,
        telegram_user_id: int,
        telegram_username: Optional[str] = None,
        referrer_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ثبت کاربر جدید در سیستم

        Args:
            telegram_user_id: شناسه تلگرام
            telegram_username: نام کاربری تلگرام
            referrer_code: کد معرف

        Returns:
            نتیجه ثبت
        """
        # بررسی موجود بودن
        existing = await self.get_user_by_telegram_id(telegram_user_id)
        if existing:
            return {
                "success": True,
                "new": False,
                "user": existing
            }

        try:
            # ایجاد کاربر جدید
            user_data = {
                "telegram_id": telegram_user_id,
                "telegram_username": telegram_username,
                "role": "user",
                "status": "active",
                "created_at": datetime.utcnow().isoformat()
            }

            if referrer_code:
                user_data["referrer_code"] = referrer_code

            result = await db.insert("user_profiles", user_data, use_admin=True)

            logger.info(f"کاربر جدید ثبت شد: {telegram_user_id}")

            return {
                "success": True,
                "new": True,
                "user": result
            }

        except Exception as e:
            logger.error(f"خطا در ثبت کاربر: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def _check_license(self, user_id: str) -> Dict[str, Any]:
        """بررسی لایسنس کاربر"""
        from ..license.manager import license_manager

        try:
            license_data = await license_manager.get_user_license(user_id)

            if not license_data:
                return {
                    "valid": False,
                    "allowed": False,
                    "reason": "license_invalid",
                    "message": get_permission_denied_message("license_invalid")
                }

            if license_data.get("status") != "active":
                return {
                    "valid": False,
                    "allowed": False,
                    "reason": "license_invalid",
                    "message": get_permission_denied_message("license_invalid")
                }

            return {"valid": True, "allowed": True, "license": license_data}

        except Exception as e:
            logger.error(f"خطا در بررسی لایسنس: {e}")
            return {
                "valid": False,
                "allowed": False,
                "reason": "license_check_failed",
                "message": "❌ خطا در بررسی لایسنس"
            }

    def _get_cached(self, telegram_user_id: int) -> Optional[Dict[str, Any]]:
        """دریافت از کش"""
        cached = self._cache.get(telegram_user_id)
        if cached:
            cached_at = cached.get("_cached_at")
            if cached_at:
                age = (datetime.utcnow() - datetime.fromisoformat(cached_at)).total_seconds()
                if age < 300:  # 5 دقیقه
                    return cached
        return None

    def _set_cache(self, telegram_user_id: int, data: Dict[str, Any]) -> None:
        """تنظیم کش"""
        data["_cached_at"] = datetime.utcnow().isoformat()
        self._cache[telegram_user_id] = data

    def _clear_cache(self, telegram_user_id: int) -> None:
        """پاک کردن کش"""
        if telegram_user_id in self._cache:
            del self._cache[telegram_user_id]


# نمونه گلوبال
rbac_service = RBACService()
