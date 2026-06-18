"""
سرویس RBAC — مدیریت کاربران و دسترسی‌ها در دیتابیس

این سرویس مسئول CRUD کاربران، role‌ها، و validation دسترسی است.
از Supabase به عنوان backend دیتابیس استفاده می‌کند.

نویسنده: MT5 Trading Team
"""

import os
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..database.connection import get_supabase_client
from ..telegram.rbac import UserRole, Permission, has_permission, ROLE_NAMES_FA
from ..core.logger import get_logger

logger = get_logger("services.rbac_service")


class RBACService:
    """
    سرویس مدیریت نقش‌ها و دسترسی‌ها

    تمام عملیات CRUD کاربران از طریق این سرویس انجام می‌شود.
    """

    def __init__(self):
        """مقداردهی اولیه سرویس"""
        self._table = "users"

    async def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        دریافت اطلاعات یک کاربر بر اساس Chat ID

        Args:
            telegram_id: شناسه تلگرام کاربر

        Returns:
            دیکشنری اطلاعات کاربر یا None
        """
        try:
            client = await get_supabase_client()
            result = client.table(self._table).select("*").eq(
                "telegram_id", telegram_id
            ).single().execute()
            return result.data if result.data else None
        except Exception as e:
            logger.error(f"خطا در دریافت کاربر {telegram_id}: {e}", exc_info=True)
            return None

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """
        دریافت لیست کامل کاربران

        Returns:
            لیست دیکشنری اطلاعات کاربران
        """
        try:
            client = await get_supabase_client()
            result = client.table(self._table).select("*").order(
                "created_at", desc=True
            ).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"خطا در دریافت لیست کاربران: {e}", exc_info=True)
            return []

    async def get_users_by_role(self, role: UserRole) -> List[Dict[str, Any]]:
        """
        دریافت کاربران بر اساس نقش

        Args:
            role: نقش مورد نظر

        Returns:
            لیست کاربران با نقش مشخص
        """
        try:
            client = await get_supabase_client()
            result = client.table(self._table).select("*").eq(
                "role", role.value
            ).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"خطا در دریافت کاربران با نقش {role.value}: {e}", exc_info=True)
            return []

    async def add_user(
        self,
        telegram_id: int,
        role: UserRole,
        added_by: int,
        username: Optional[str] = None,
        license_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        اضافه کردن کاربر جدید

        Args:
            telegram_id: شناسه تلگرام
            role: نقش کاربر
            added_by: Chat ID کسی که کاربر را اضافه کرده
            username: نام کاربری تلگرام
            license_key: کلید لایسنس (اختیاری)

        Returns:
            دیکشنری کاربر ایجاد شده

        Raises:
            ValueError: اگر کاربر از قبل وجود داشته باشد
        """
        existing = await self.get_user(telegram_id)
        if existing:
            raise ValueError(f"کاربر {telegram_id} از قبل وجود دارد")

        try:
            client = await get_supabase_client()
            data = {
                "telegram_id": telegram_id,
                "role": role.value,
                "is_active": True,
                "added_by": added_by,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }
            if username:
                data["username"] = username
            if license_key:
                data["license_key"] = license_key

            result = client.table(self._table).insert(data).execute()
            logger.info(f"کاربر {telegram_id} با نقش {role.value} اضافه شد")
            return result.data[0] if result.data else data
        except Exception as e:
            logger.error(f"خطا در اضافه کردن کاربر {telegram_id}: {e}", exc_info=True)
            raise

    async def remove_user(self, telegram_id: int, removed_by: int) -> bool:
        """
        حذف کاربر (غیرفعال کردن — soft delete)

        Args:
            telegram_id: شناسه تلگرام
            removed_by: Chat ID کسی که حذف کرده

        Returns:
            True در صورت موفقیت
        """
        try:
            client = await get_supabase_client()
            client.table(self._table).update({
                "is_active": False,
                "deactivated_by": removed_by,
                "deactivated_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("telegram_id", telegram_id).execute()
            logger.info(f"کاربر {telegram_id} توسط {removed_by} حذف (غیرفعال) شد")
            return True
        except Exception as e:
            logger.error(f"خطا در حذف کاربر {telegram_id}: {e}", exc_info=True)
            raise

    async def update_user_role(
        self,
        telegram_id: int,
        new_role: UserRole,
        changed_by: int
    ) -> bool:
        """
        تغییر نقش کاربر

        Args:
            telegram_id: شناسه تلگرام
            new_role: نقش جدید
            changed_by: Chat ID کسی که تغییر داده

        Returns:
            True در صورت موفقیت
        """
        try:
            client = await get_supabase_client()
            client.table(self._table).update({
                "role": new_role.value,
                "role_changed_by": changed_by,
                "role_changed_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }).eq("telegram_id", telegram_id).execute()
            logger.info(
                f"نقش کاربر {telegram_id} به {new_role.value} توسط {changed_by} تغییر یافت"
            )
            return True
        except Exception as e:
            logger.error(
                f"خطا در تغییر نقش کاربر {telegram_id}: {e}", exc_info=True
            )
            raise

    async def get_user_role(self, telegram_id: int) -> Optional[UserRole]:
        """
        دریافت نقش کاربر

        Args:
            telegram_id: شناسه تلگرام

        Returns:
            نقش کاربر یا None
        """
        user = await self.get_user(telegram_id)
        if not user:
            return None
        try:
            return UserRole(user.get("role", "viewer"))
        except ValueError:
            return UserRole.VIEWER

    async def check_permission(
        self,
        telegram_id: int,
        permission: Permission
    ) -> bool:
        """
        بررسی اینکه آیا کاربر دسترسی مشخصی دارد

        Args:
            telegram_id: شناسه تلگرام
            permission: دسترسی مورد بررسی

        Returns:
            True اگر کاربر دسترسی داشته باشد
        """
        role = await self.get_user_role(telegram_id)
        if not role:
            return False
        return has_permission(role, permission)

    async def is_user_active(self, telegram_id: int) -> bool:
        """
        بررسی فعال بودن کاربر

        Args:
            telegram_id: شناسه تلگرام

        Returns:
            True اگر کاربر فعال باشد
        """
        user = await self.get_user(telegram_id)
        return bool(user and user.get("is_active"))

    async def get_users_stats(self) -> Dict[str, Any]:
        """
        آمار کلی کاربران به تفکیک نقش

        Returns:
            دیکشنری آمار
        """
        try:
            users = await self.get_all_users()
            stats: Dict[str, int] = {}
            active_count = 0
            for u in users:
                role_val = u.get("role", "viewer")
                stats[role_val] = stats.get(role_val, 0) + 1
                if u.get("is_active"):
                    active_count += 1
            return {
                "total": len(users),
                "active": active_count,
                "inactive": len(users) - active_count,
                "by_role": stats,
            }
        except Exception as e:
            logger.error(f"خطا در دریافت آمار کاربران: {e}", exc_info=True)
            return {"total": 0, "active": 0, "inactive": 0, "by_role": {}}


# Singleton
rbac_service = RBACService()
