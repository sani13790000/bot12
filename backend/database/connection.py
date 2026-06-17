"""
اتصال به دیتابیس Supabase

این ماژول اتصال به Supabase را مدیریت می‌کند.
تمام عملیات دیتابیس از طریق این ماژول انجام می‌شود.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import httpx
from postgrest import PostgrestClient
from supabase import create_client, Client
from ..core.config import settings
from ..core.logger import get_logger
from ..core.exceptions import DatabaseError, RecordNotFoundError

logger = get_logger("database")


class SupabaseManager:
    """
    مدیر Supabase

    این کلاس تمام عملیات دیتابیس را مدیریت می‌کند.
    از Supabase Client SDK استفاده می‌کند.
    """

    _instance: Optional['SupabaseManager'] = None
    _client: Optional[Client] = None
    _admin_client: Optional[Client] = None

    def __new__(cls):
        """پیاده‌سازی Singleton"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """مقداردهی اولیه"""
        if self._client is not None:
            return

        try:
            # کلاینت عادی
            self._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_ANON_KEY
            )
            logger.info("اتصال به Supabase برقرار شد (کلاینت عادی)")

            # کلاینت ادمین (دسترسی کامل)
            self._admin_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
            logger.info("اتصال به Supabase برقرار شد (کلاینت ادمین)")

        except Exception as e:
            logger.error(f"خطا در اتصال به Supabase: {e}")
            raise DatabaseError(f"خطای اتصال به دیتابیس: {e}")

    @property
    def client(self) -> Client:
        """کلاینت عادی (با RLS)"""
        if self._client is None:
            raise DatabaseError("کلاینت Supabase مقداردهی نشده است")
        return self._client

    @property
    def admin(self) -> Client:
        """کلاینت ادمین (بدون RLS)"""
        if self._admin_client is None:
            raise DatabaseError("کلاینت ادمین Supabase مقداردهی نشده است")
        return self._admin_client

    # =====================================================
    # عملیات رکورد
    # =====================================================

    async def select_one(
        self,
        table: str,
        filters: Dict[str, Any],
        use_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        انتخاب یک رکورد

        Args:
            table: نام جدول
            filters: فیلترها
            use_admin: استفاده از کلاینت ادمین

        Returns:
            رکورد یافت شده یا None
        """
        try:
            client = self.admin if use_admin else self.client
            query = client.table(table).select("*")

            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.limit(1).execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None

        except Exception as e:
            logger.error(f"خطا در select_one از {table}: {e}")
            raise DatabaseError(f"خطا در خواندن از دیتابیس: {e}")

    async def select_many(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = None,
        order_desc: bool = False,
        limit: int = 100,
        offset: int = 0,
        use_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        انتخاب چندین رکورد

        Args:
            table: نام جدول
            filters: فیلترها (اختیاری)
            order_by: مرتب‌سازی (اختیاری)
            order_desc: نزولی
            limit: حداکثر تعداد
            offset: offset
            use_admin: استفاده از کلاینت ادمین

        Returns:
            لیست رکوردها
        """
        try:
            client = self.admin if use_admin else self.client
            query = client.table(table).select("*")

            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            if order_by:
                query = query.order(order_by, desc=order_desc)

            response = query.range(offset, offset + limit - 1).execute()
            return response.data or []

        except Exception as e:
            logger.error(f"خطا در select_many از {table}: {e}")
            raise DatabaseError(f"خطا در خواندن از دیتابیس: {e}")

    async def insert(
        self,
        table: str,
        data: Dict[str, Any],
        use_admin: bool = False
    ) -> Dict[str, Any]:
        """
        درج رکورد جدید

        Args:
            table: نام جدول
            data: داده‌های رکورد
            use_admin: استفاده از کلاینت ادمین

        Returns:
            رکورد درج شده
        """
        try:
            client = self.admin if use_admin else self.client
            response = client.table(table).insert(data).execute()

            if response.data:
                logger.debug(f"رکورد در جدول {table} درج شد")
                return response.data[0]
            raise DatabaseError("رکورد درج نشد")

        except Exception as e:
            logger.error(f"خطا در insert در {table}: {e}")
            raise DatabaseError(f"خطا در درج در دیتابیس: {e}")

    async def update(
        self,
        table: str,
        filters: Dict[str, Any],
        data: Dict[str, Any],
        use_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """
        به‌روزرسانی رکوردها

        Args:
            table: نام جدول
            filters: فیلترها برای شناسایی رکوردها
            data: داده‌های جدید
            use_admin: استفاده از کلاینت ادمین

        Returns:
            رکوردهای به‌روزرسانی شده
        """
        try:
            client = self.admin if use_admin else self.client
            query = client.table(table).update(data)

            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.execute()

            logger.debug(f"رکوردهای جدول {table} به‌روزرسانی شدند")
            return response.data or []

        except Exception as e:
            logger.error(f"خطا در update در {table}: {e}")
            raise DatabaseError(f"خطا در به‌روزرسانی دیتابیس: {e}")

    async def delete(
        self,
        table: str,
        filters: Dict[str, Any],
        use_admin: bool = False
    ) -> bool:
        """
        حذف رکوردها

        Args:
            table: نام جدول
            filters: فیلترها
            use_admin: استفاده از کلاینت ادمین

        Returns:
            True اگر موفق بود
        """
        try:
            client = self.admin if use_admin else self.client
            query = client.table(table).delete()

            for key, value in filters.items():
                query = query.eq(key, value)

            response = query.execute()
            logger.debug(f"رکوردهای جدول {table} حذف شدند")
            return True

        except Exception as e:
            logger.error(f"خطا در delete از {table}: {e}")
            raise DatabaseError(f"خطا در حذف از دیتابیس: {e}")

    async def count(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        use_admin: bool = False
    ) -> int:
        """
        شمارش رکوردها

        Args:
            table: نام جدول
            filters: فیلترها
            use_admin: استفاده از کلاینت ادمین

        Returns:
            تعداد رکوردها
        """
        try:
            client = self.admin if use_admin else self.client
            query = client.table(table).select("*", count="exact")

            if filters:
                for key, value in filters.items():
                    query = query.eq(key, value)

            response = query.limit(1).execute()
            return response.count or 0

        except Exception as e:
            logger.error(f"خطا در count از {table}: {e}")
            return 0

    # =====================================================
    # عملیات پیشرفته
    # =====================================================

    async def execute_rpc(
        self,
        function_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        اجرای تابع RPC

        Args:
            function_name: نام تابع
            params: پارامترها

        Returns:
            نتیجه تابع
        """
        try:
            response = self.client.rpc(function_name, params or {}).execute()
            return response.data

        except Exception as e:
            logger.error(f"خطا در اجرای RPC {function_name}: {e}")
            raise DatabaseError(f"خطا در اجرای تابع دیتابیس: {e}")

    async def upsert(
        self,
        table: str,
        data: Dict[str, Any],
        on_conflict: str,
        use_admin: bool = False
    ) -> Dict[str, Any]:
        """
        درج یا به‌روزرسانی

        Args:
            table: نام جدول
            data: داده‌ها
            on_conflict: ستون برای بررسی تکرار
            use_admin: استفاده از کلاینت ادمین

        Returns:
            رکورد
        """
        try:
            client = self.admin if use_admin else self.client
            response = client.table(table).upsert(
                data,
                on_conflict=on_conflict
            ).execute()

            if response.data:
                return response.data[0]
            raise DatabaseError("عملیات upsert ناموفق بود")

        except Exception as e:
            logger.error(f"خطا در upsert در {table}: {e}")
            raise DatabaseError(f"خطا در upsert: {e}")


# نمونه گلوبال
db = SupabaseManager()


def get_db() -> SupabaseManager:
    """دریافت نمونه دیتابیس"""
    return db
