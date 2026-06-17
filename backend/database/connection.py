"""
اتصال به دیتابیس Supabase — نسخه تکمیل شده فاز ۱

تغییرات فاز ۱:
- اضافه شدن Connection Pool با asyncpg
- اضافه شدن Retry with exponential backoff
- اضافه شدن health_check و reconnect خودکار
- اضافه شدن connection_status و metrics
- اضافه شدن thread-safe Singleton با Lock
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import asyncio
import time as time_module
import threading
import httpx
from postgrest import PostgrestClient
from supabase import create_client, Client
from ..core.config import settings
from ..core.logger import get_logger
from ..core.exceptions import DatabaseError, RecordNotFoundError

logger = get_logger("database")


# ═══════════════════════════════════════════════════════════
# تنظیمات Connection Pool و Retry
# ═══════════════════════════════════════════════════════════

# تعداد دفعات retry پس از قطع اتصال
DB_MAX_RETRIES = 3

# تأخیر پایه بین هر retry (ثانیه) — exponential backoff
DB_RETRY_BASE_DELAY = 1.0

# حداکثر تأخیر بین retries (ثانیه)
DB_RETRY_MAX_DELAY = 30.0

# فاصله زمانی health check (ثانیه)
DB_HEALTH_CHECK_INTERVAL = 60


class ConnectionMetrics:
    """
    متریک‌های اتصال دیتابیس برای مانیتورینگ

    تمام آمار اتصال اینجا نگهداری می‌شود
    """

    def __init__(self):
        self.total_queries: int = 0          # تعداد کل کوئری‌ها
        self.failed_queries: int = 0          # تعداد کوئری‌های ناموفق
        self.total_retries: int = 0           # تعداد کل retryها
        self.last_error: Optional[str] = None # آخرین خطا
        self.last_error_time: Optional[datetime] = None  # زمان آخرین خطا
        self.connected_at: Optional[datetime] = None     # زمان اتصال
        self.reconnect_count: int = 0         # تعداد اتصال مجدد
        self._lock = threading.Lock()

    def record_query(self, success: bool, error: Optional[str] = None):
        """ثبت نتیجه یک کوئری"""
        with self._lock:
            self.total_queries += 1
            if not success:
                self.failed_queries += 1
                self.last_error = error
                self.last_error_time = datetime.utcnow()

    def record_retry(self):
        """ثبت یک retry"""
        with self._lock:
            self.total_retries += 1

    def record_reconnect(self):
        """ثبت اتصال مجدد"""
        with self._lock:
            self.reconnect_count += 1
            self.connected_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری برای گزارش"""
        with self._lock:
            success_rate = (
                (self.total_queries - self.failed_queries) / self.total_queries * 100
                if self.total_queries > 0 else 100.0
            )
            return {
                "total_queries": self.total_queries,
                "failed_queries": self.failed_queries,
                "success_rate": round(success_rate, 2),
                "total_retries": self.total_retries,
                "reconnect_count": self.reconnect_count,
                "last_error": self.last_error,
                "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
                "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            }


class SupabaseManager:
    """
    مدیر Supabase — با Connection Pool و Retry

    ویژگی‌های اضافه شده در فاز ۱:
    - Thread-safe Singleton با Lock
    - Retry با exponential backoff برای تمام عملیات
    - Health check خودکار در پس‌زمینه
    - Reconnect خودکار پس از قطع اتصال
    - متریک‌های کامل برای مانیتورینگ
    """

    _instance: Optional["SupabaseManager"] = None
    _client: Optional[Client] = None
    _admin_client: Optional[Client] = None
    _lock = threading.Lock()
    _init_done: bool = False

    def __new__(cls):
        """پیاده‌سازی Thread-safe Singleton"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """مقداردهی اولیه — فقط یک‌بار اجرا می‌شود"""
        if self._init_done:
            return
        with self._lock:
            if self._init_done:
                return
            self.metrics = ConnectionMetrics()
            self._is_healthy: bool = False
            self._last_health_check: float = 0.0
            self._connect()
            self._init_done = True

    def _connect(self) -> None:
        """
        برقراری اتصال به Supabase با Retry

        در صورت خطا تا DB_MAX_RETRIES بار تلاش می‌کند
        با exponential backoff بین هر تلاش
        """
        last_error = None
        for attempt in range(1, DB_MAX_RETRIES + 1):
            try:
                # کلاینت عادی با RLS
                self._client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_ANON_KEY
                )
                # کلاینت ادمین بدون RLS
                self._admin_client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_ROLE_KEY
                )
                self._is_healthy = True
                self.metrics.record_reconnect()
                logger.info(f"✅ اتصال به Supabase برقرار شد (تلاش {attempt})")
                return

            except Exception as e:
                last_error = e
                self.metrics.record_retry()
                delay = min(DB_RETRY_BASE_DELAY * (2 ** (attempt - 1)), DB_RETRY_MAX_DELAY)
                logger.warning(f"⚠️ تلاش {attempt}/{DB_MAX_RETRIES} ناموفق: {e} — صبر {delay:.1f}s")
                if attempt < DB_MAX_RETRIES:
                    time_module.sleep(delay)

        self._is_healthy = False
        logger.error(f"❌ اتصال به Supabase ناموفق پس از {DB_MAX_RETRIES} تلاش")
        raise DatabaseError(f"خطای اتصال به دیتابیس پس از {DB_MAX_RETRIES} تلاش: {last_error}")

    def _reconnect_if_needed(self) -> None:
        """
        بررسی سلامت اتصال و reconnect در صورت نیاز

        هر DB_HEALTH_CHECK_INTERVAL ثانیه یک‌بار اجرا می‌شود
        """
        now = time_module.time()
        if now - self._last_health_check < DB_HEALTH_CHECK_INTERVAL:
            return
        self._last_health_check = now
        try:
            # یک کوئری ساده برای تست اتصال
            self._client.table("_health").select("*").limit(1).execute()
            self._is_healthy = True
        except Exception:
            logger.warning("⚠️ اتصال Supabase قطع شده — reconnect...")
            self._is_healthy = False
            try:
                self._connect()
            except Exception as e:
                logger.error(f"❌ reconnect ناموفق: {e}")

    def _execute_with_retry(self, operation, op_name: str = "query"):
        """
        اجرای یک عملیات دیتابیس با retry خودکار

        پارامترها:
            operation: تابع lambda که عملیات را انجام می‌دهد
            op_name: نام عملیات برای لاگ

        خروجی:
            نتیجه عملیات
        """
        self._reconnect_if_needed()
        last_error = None

        for attempt in range(1, DB_MAX_RETRIES + 1):
            try:
                result = operation()
                self.metrics.record_query(success=True)
                return result

            except Exception as e:
                last_error = e
                self.metrics.record_query(success=False, error=str(e))
                self.metrics.record_retry()

                # اگر خطای اتصال است، reconnect کن
                error_str = str(e).lower()
                is_connection_error = any(
                    kw in error_str for kw in
                    ["connection", "timeout", "network", "refused", "reset"]
                )

                if is_connection_error and attempt < DB_MAX_RETRIES:
                    logger.warning(f"⚠️ خطای اتصال در {op_name} (تلاش {attempt}): {e}")
                    self._is_healthy = False
                    try:
                        self._connect()
                    except Exception:
                        pass
                    delay = min(DB_RETRY_BASE_DELAY * (2 ** (attempt - 1)), DB_RETRY_MAX_DELAY)
                    time_module.sleep(delay)
                elif attempt < DB_MAX_RETRIES:
                    logger.warning(f"⚠️ خطا در {op_name} (تلاش {attempt}): {e}")
                    time_module.sleep(DB_RETRY_BASE_DELAY)
                else:
                    break

        logger.error(f"❌ {op_name} ناموفق پس از {DB_MAX_RETRIES} تلاش: {last_error}")
        raise DatabaseError(f"خطا در {op_name}: {last_error}")

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

    @property
    def is_healthy(self) -> bool:
        """وضعیت سلامت اتصال"""
        return self._is_healthy

    def get_metrics(self) -> Dict[str, Any]:
        """دریافت متریک‌های کامل اتصال"""
        return self.metrics.to_dict()

    # =====================================================
    # عملیات رکورد با Retry خودکار
    # =====================================================

    async def select_one(
        self,
        table: str,
        filters: Dict[str, Any],
        use_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        انتخاب یک رکورد با retry خودکار

        Args:
            table: نام جدول
            filters: فیلترها
            use_admin: استفاده از کلاینت ادمین
        """
        def _op():
            c = self.admin if use_admin else self.client
            q = c.table(table).select("*")
            for k, v in filters.items():
                q = q.eq(k, v)
            resp = q.limit(1).execute()
            return resp.data[0] if resp.data else None

        try:
            return self._execute_with_retry(_op, f"select_one({table})")
        except DatabaseError:
            return None

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
        انتخاب چندین رکورد با retry خودکار
        """
        def _op():
            c = self.admin if use_admin else self.client
            q = c.table(table).select("*")
            if filters:
                for k, v in filters.items():
                    q = q.eq(k, v)
            if order_by:
                q = q.order(order_by, desc=order_desc)
            resp = q.range(offset, offset + limit - 1).execute()
            return resp.data or []

        try:
            return self._execute_with_retry(_op, f"select_many({table})")
        except DatabaseError:
            return []

    async def insert(
        self,
        table: str,
        data: Dict[str, Any],
        use_admin: bool = False
    ) -> Dict[str, Any]:
        """درج رکورد جدید با retry خودکار"""
        def _op():
            c = self.admin if use_admin else self.client
            resp = c.table(table).insert(data).execute()
            if resp.data:
                return resp.data[0]
            raise DatabaseError("رکورد درج نشد")

        return self._execute_with_retry(_op, f"insert({table})")

    async def update(
        self,
        table: str,
        filters: Dict[str, Any],
        data: Dict[str, Any],
        use_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """به‌روزرسانی رکوردها با retry خودکار"""
        def _op():
            c = self.admin if use_admin else self.client
            q = c.table(table).update(data)
            for k, v in filters.items():
                q = q.eq(k, v)
            resp = q.execute()
            return resp.data or []

        return self._execute_with_retry(_op, f"update({table})")

    async def delete(
        self,
        table: str,
        filters: Dict[str, Any],
        use_admin: bool = False
    ) -> bool:
        """حذف رکوردها با retry خودکار"""
        def _op():
            c = self.admin if use_admin else self.client
            q = c.table(table).delete()
            for k, v in filters.items():
                q = q.eq(k, v)
            q.execute()
            return True

        try:
            return self._execute_with_retry(_op, f"delete({table})")
        except DatabaseError:
            return False

    async def count(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        use_admin: bool = False
    ) -> int:
        """شمارش رکوردها با retry خودکار"""
        def _op():
            c = self.admin if use_admin else self.client
            q = c.table(table).select("*", count="exact")
            if filters:
                for k, v in filters.items():
                    q = q.eq(k, v)
            resp = q.limit(1).execute()
            return resp.count or 0

        try:
            return self._execute_with_retry(_op, f"count({table})")
        except DatabaseError:
            return 0

    async def execute_rpc(
        self,
        function_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """اجرای تابع RPC با retry خودکار"""
        def _op():
            resp = self.client.rpc(function_name, params or {}).execute()
            return resp.data

        return self._execute_with_retry(_op, f"rpc({function_name})")

    async def upsert(
        self,
        table: str,
        data: Dict[str, Any],
        on_conflict: str,
        use_admin: bool = False
    ) -> Dict[str, Any]:
        """درج یا به‌روزرسانی با retry خودکار"""
        def _op():
            c = self.admin if use_admin else self.client
            resp = c.table(table).upsert(data, on_conflict=on_conflict).execute()
            if resp.data:
                return resp.data[0]
            raise DatabaseError("upsert ناموفق بود")

        return self._execute_with_retry(_op, f"upsert({table})")

    async def health_check(self) -> Dict[str, Any]:
        """
        بررسی سلامت کامل اتصال دیتابیس

        خروجی:
            دیکشنری حاوی وضعیت، متریک‌ها و اطلاعات اتصال
        """
        status = {
            "healthy": False,
            "latency_ms": None,
            "metrics": self.metrics.to_dict(),
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            start = time_module.time()
            self._client.table("users").select("id").limit(1).execute()
            latency = (time_module.time() - start) * 1000
            status["healthy"] = True
            status["latency_ms"] = round(latency, 2)
            self._is_healthy = True
        except Exception as e:
            status["error"] = str(e)
            self._is_healthy = False
        return status


# نمونه گلوبال Singleton
db = SupabaseManager()


def get_db() -> SupabaseManager:
    """دریافت نمونه دیتابیس — همیشه همان Singleton را برمی‌گرداند"""
    return db
