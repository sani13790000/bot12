"""
Ø§ØªØµØ§Ù Ø¨Ù Ø¯ÛØªØ§Ø¨ÛØ³ Supabase â ÙØ³Ø®Ù ØªÚ©ÙÛÙ Ø´Ø¯Ù ÙØ§Ø² Û±

ØªØºÛÛØ±Ø§Øª ÙØ§Ø² Û±:
- Ø§Ø¶Ø§ÙÙ Ø´Ø¯Ù Connection Pool Ø¨Ø§ asyncpg
- Ø§Ø¶Ø§ÙÙ Ø´Ø¯Ù Retry with exponential backoff
- Ø§Ø¶Ø§ÙÙ Ø´Ø¯Ù health_check Ù reconnect Ø®ÙØ¯Ú©Ø§Ø±
- Ø§Ø¶Ø§ÙÙ Ø´Ø¯Ù connection_status Ù metrics
- Ø§Ø¶Ø§ÙÙ Ø´Ø¯Ù thread-safe Singleton Ø¨Ø§ Lock
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


# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
# ØªÙØ¸ÛÙØ§Øª Connection Pool Ù Retry
# âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

# ØªØ¹Ø¯Ø§Ø¯ Ø¯ÙØ¹Ø§Øª retry Ù¾Ø³ Ø§Ø² ÙØ·Ø¹ Ø§ØªØµØ§Ù
DB_MAX_RETRIES = 3

# ØªØ£Ø®ÛØ± Ù¾Ø§ÛÙ Ø¨ÛÙ ÙØ± retry (Ø«Ø§ÙÛÙ) â exponential backoff
DB_RETRY_BASE_DELAY = 1.0

# Ø­Ø¯Ø§Ú©Ø«Ø± ØªØ£Ø®ÛØ± Ø¨ÛÙ retries (Ø«Ø§ÙÛÙ)
DB_RETRY_MAX_DELAY = 30.0

# ÙØ§ØµÙÙ Ø²ÙØ§ÙÛ health check (Ø«Ø§ÙÛÙ)
DB_HEALTH_CHECK_INTERVAL = 60


class ConnectionMetrics:
    """
    ÙØªØ±ÛÚ©âÙØ§Û Ø§ØªØµØ§Ù Ø¯ÛØªØ§Ø¨ÛØ³ Ø¨Ø±Ø§Û ÙØ§ÙÛØªÙØ±ÛÙÚ¯

    ØªÙØ§Ù Ø¢ÙØ§Ø± Ø§ØªØµØ§Ù Ø§ÛÙØ¬Ø§ ÙÚ¯ÙØ¯Ø§Ø±Û ÙÛâØ´ÙØ¯
    """

    def __init__(self):
        self.total_queries: int = 0          # ØªØ¹Ø¯Ø§Ø¯ Ú©Ù Ú©ÙØ¦Ø±ÛâÙØ§
        self.failed_queries: int = 0          # ØªØ¹Ø¯Ø§Ø¯ Ú©ÙØ¦Ø±ÛâÙØ§Û ÙØ§ÙÙÙÙ
        self.total_retries: int = 0           # ØªØ¹Ø¯Ø§Ø¯ Ú©Ù retryÙØ§
        self.last_error: Optional[str] = None # Ø¢Ø®Ø±ÛÙ Ø®Ø·Ø§
        self.last_error_time: Optional[datetime] = None  # Ø²ÙØ§Ù Ø¢Ø®Ø±ÛÙ Ø®Ø·Ø§
        self.connected_at: Optional[datetime] = None     # Ø²ÙØ§Ù Ø§ØªØµØ§Ù
        self.reconnect_count: int = 0         # ØªØ¹Ø¯Ø§Ø¯ Ø§ØªØµØ§Ù ÙØ¬Ø¯Ø¯
        self._lock = threading.Lock()

    def record_query(self, success: bool, error: Optional[str] = None):
        """Ø«Ø¨Øª ÙØªÛØ¬Ù ÛÚ© Ú©ÙØ¦Ø±Û"""
        with self._lock:
            self.total_queries += 1
            if not success:
                self.failed_queries += 1
                self.last_error = error
                self.last_error_time = datetime.utcnow()

    def record_retry(self):
        """Ø«Ø¨Øª ÛÚ© retry"""
        with self._lock:
            self.total_retries += 1

    def record_reconnect(self):
        """Ø«Ø¨Øª Ø§ØªØµØ§Ù ÙØ¬Ø¯Ø¯"""
        with self._lock:
            self.reconnect_count += 1
            self.connected_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """ØªØ¨Ø¯ÛÙ Ø¨Ù Ø¯ÛÚ©Ø´ÙØ±Û Ø¨Ø±Ø§Û Ú¯Ø²Ø§Ø±Ø´"""
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
    ÙØ¯ÛØ± Supabase â Ø¨Ø§ Connection Pool Ù Retry

    ÙÛÚÚ¯ÛâÙØ§Û Ø§Ø¶Ø§ÙÙ Ø´Ø¯Ù Ø¯Ø± ÙØ§Ø² Û±:
    - Thread-safe Singleton Ø¨Ø§ Lock
    - Retry Ø¨Ø§ exponential backoff Ø¨Ø±Ø§Û ØªÙØ§Ù Ø¹ÙÙÛØ§Øª
    - Health check Ø®ÙØ¯Ú©Ø§Ø± Ø¯Ø± Ù¾Ø³âØ²ÙÛÙÙ
    - Reconnect Ø®ÙØ¯Ú©Ø§Ø± Ù¾Ø³ Ø§Ø² ÙØ·Ø¹ Ø§ØªØµØ§Ù
    - ÙØªØ±ÛÚ©âÙØ§Û Ú©Ø§ÙÙ Ø¨Ø±Ø§Û ÙØ§ÙÛØªÙØ±ÛÙÚ¯
    """

    _instance: Optional["SupabaseManager"] = None
    _client: Optional[Client] = None
    _admin_client: Optional[Client] = None
    _lock = threading.Lock()
    _init_done: bool = False

    def __new__(cls):
        """Ù¾ÛØ§Ø¯ÙâØ³Ø§Ø²Û Thread-safe Singleton"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """ÙÙØ¯Ø§Ø±Ø¯ÙÛ Ø§ÙÙÛÙ â ÙÙØ· ÛÚ©âØ¨Ø§Ø± Ø§Ø¬Ø±Ø§ ÙÛâØ´ÙØ¯"""
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
        Ø¨Ø±ÙØ±Ø§Ø±Û Ø§ØªØµØ§Ù Ø¨Ù Supabase Ø¨Ø§ Retry

        Ø¯Ø± ØµÙØ±Øª Ø®Ø·Ø§ ØªØ§ DB_MAX_RETRIES Ø¨Ø§Ø± ØªÙØ§Ø´ ÙÛâÚ©ÙØ¯
        Ø¨Ø§ exponential backoff Ø¨ÛÙ ÙØ± ØªÙØ§Ø´
        """
        last_error = None
        for attempt in range(1, DB_MAX_RETRIES + 1):
            try:
                # Ú©ÙØ§ÛÙØª Ø¹Ø§Ø¯Û Ø¨Ø§ RLS
                self._client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_ANON_KEY
                )
                # Ú©ÙØ§ÛÙØª Ø§Ø¯ÙÛÙ Ø¨Ø¯ÙÙ RLS
                self._admin_client = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_SERVICE_ROLE_KEY
                )
                self._is_healthy = True
                self.metrics.record_reconnect()
                logger.info(f"â Ø§ØªØµØ§Ù Ø¨Ù Supabase Ø¨Ø±ÙØ±Ø§Ø± Ø´Ø¯ (ØªÙØ§Ø´ {attempt})")
                return

            except Exception as e:
                last_error = e
                self.metrics.record_retry()
                delay = min(DB_RETRY_BASE_DELAY * (2 ** (attempt - 1)), DB_RETRY_MAX_DELAY)
                logger.warning(f"â ï¸ ØªÙØ§Ø´ {attempt}/{DB_MAX_RETRIES} ÙØ§ÙÙÙÙ: {e} â ØµØ¨Ø± {delay:.1f}s")
                if attempt < DB_MAX_RETRIES:
                    time_module.sleep(delay)

        self._is_healthy = False
        logger.error(f"â Ø§ØªØµØ§Ù Ø¨Ù Supabase ÙØ§ÙÙÙÙ Ù¾Ø³ Ø§Ø² {DB_MAX_RETRIES} ØªÙØ§Ø´")
        raise DatabaseError(f"Ø®Ø·Ø§Û Ø§ØªØµØ§Ù Ø¨Ù Ø¯ÛØªØ§Ø¨ÛØ³ Ù¾Ø³ Ø§Ø² {DB_MAX_RETRIES} ØªÙØ§Ø´: {last_error}")

    def _reconnect_if_needed(self) -> None:
        """
        Ø¨Ø±Ø±Ø³Û Ø³ÙØ§ÙØª Ø§ØªØµØ§Ù Ù reconnect Ø¯Ø± ØµÙØ±Øª ÙÛØ§Ø²

        ÙØ± DB_HEALTH_CHECK_INTERVAL Ø«Ø§ÙÛÙ ÛÚ©âØ¨Ø§Ø± Ø§Ø¬Ø±Ø§ ÙÛâØ´ÙØ¯
        """
        now = time_module.time()
        if now - self._last_health_check < DB_HEALTH_CHECK_INTERVAL:
            return
        self._last_health_check = now
        try:
            # ÛÚ© Ú©ÙØ¦Ø±Û Ø³Ø§Ø¯Ù Ø¨Ø±Ø§Û ØªØ³Øª Ø§ØªØµØ§Ù
            self._client.table("_health").select("*").limit(1).execute()
            self._is_healthy = True
        except Exception:
            logger.warning("â ï¸ Ø§ØªØµØ§Ù Supabase ÙØ·Ø¹ Ø´Ø¯Ù â reconnect...")
            self._is_healthy = False
            try:
                self._connect()
            except Exception as e:
                logger.error(f"â reconnect ÙØ§ÙÙÙÙ: {e}")

    def _execute_with_retry(self, operation, op_name: str = "query"):
        """
        Ø§Ø¬Ø±Ø§Û ÛÚ© Ø¹ÙÙÛØ§Øª Ø¯ÛØªØ§Ø¨ÛØ³ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±

        Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§:
            operation: ØªØ§Ø¨Ø¹ lambda Ú©Ù Ø¹ÙÙÛØ§Øª Ø±Ø§ Ø§ÙØ¬Ø§Ù ÙÛâØ¯ÙØ¯
            op_name: ÙØ§Ù Ø¹ÙÙÛØ§Øª Ø¨Ø±Ø§Û ÙØ§Ú¯

        Ø®Ø±ÙØ¬Û:
            ÙØªÛØ¬Ù Ø¹ÙÙÛØ§Øª
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

                # Ø§Ú¯Ø± Ø®Ø·Ø§Û Ø§ØªØµØ§Ù Ø§Ø³ØªØ reconnect Ú©Ù
                error_str = str(e).lower()
                is_connection_error = any(
                    kw in error_str for kw in
                    ["connection", "timeout", "network", "refused", "reset"]
                )

                if is_connection_error and attempt < DB_MAX_RETRIES:
                    logger.warning(f"â ï¸ Ø®Ø·Ø§Û Ø§ØªØµØ§Ù Ø¯Ø± {op_name} (ØªÙØ§Ø´ {attempt}): {e}")
                    self._is_healthy = False
                    try:
                        self._connect()
                    except Exception as reconnect_err:
                        logger.error(
                            f"⚠️ reconnect در حین retry ناموفق: {reconnect_err}",
                            exc_info=True,
                        )
                    delay = min(DB_RETRY_BASE_DELAY * (2 ** (attempt - 1)), DB_RETRY_MAX_DELAY)
                    time_module.sleep(delay)
                elif attempt < DB_MAX_RETRIES:
                    logger.warning(f"â ï¸ Ø®Ø·Ø§ Ø¯Ø± {op_name} (ØªÙØ§Ø´ {attempt}): {e}")
                    time_module.sleep(DB_RETRY_BASE_DELAY)
                else:
                    break

        logger.error(f"â {op_name} ÙØ§ÙÙÙÙ Ù¾Ø³ Ø§Ø² {DB_MAX_RETRIES} ØªÙØ§Ø´: {last_error}")
        raise DatabaseError(f"Ø®Ø·Ø§ Ø¯Ø± {op_name}: {last_error}")

    @property
    def client(self) -> Client:
        """Ú©ÙØ§ÛÙØª Ø¹Ø§Ø¯Û (Ø¨Ø§ RLS)"""
        if self._client is None:
            raise DatabaseError("Ú©ÙØ§ÛÙØª Supabase ÙÙØ¯Ø§Ø±Ø¯ÙÛ ÙØ´Ø¯Ù Ø§Ø³Øª")
        return self._client

    @property
    def admin(self) -> Client:
        """Ú©ÙØ§ÛÙØª Ø§Ø¯ÙÛÙ (Ø¨Ø¯ÙÙ RLS)"""
        if self._admin_client is None:
            raise DatabaseError("Ú©ÙØ§ÛÙØª Ø§Ø¯ÙÛÙ Supabase ÙÙØ¯Ø§Ø±Ø¯ÙÛ ÙØ´Ø¯Ù Ø§Ø³Øª")
        return self._admin_client

    @property
    def is_healthy(self) -> bool:
        """ÙØ¶Ø¹ÛØª Ø³ÙØ§ÙØª Ø§ØªØµØ§Ù"""
        return self._is_healthy

    def get_metrics(self) -> Dict[str, Any]:
        """Ø¯Ø±ÛØ§ÙØª ÙØªØ±ÛÚ©âÙØ§Û Ú©Ø§ÙÙ Ø§ØªØµØ§Ù"""
        return self.metrics.to_dict()

    # =====================================================
    # Ø¹ÙÙÛØ§Øª Ø±Ú©ÙØ±Ø¯ Ø¨Ø§ Retry Ø®ÙØ¯Ú©Ø§Ø±
    # =====================================================

    async def select_one(
        self,
        table: str,
        filters: Dict[str, Any],
        use_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Ø§ÙØªØ®Ø§Ø¨ ÛÚ© Ø±Ú©ÙØ±Ø¯ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±

        Args:
            table: ÙØ§Ù Ø¬Ø¯ÙÙ
            filters: ÙÛÙØªØ±ÙØ§
            use_admin: Ø§Ø³ØªÙØ§Ø¯Ù Ø§Ø² Ú©ÙØ§ÛÙØª Ø§Ø¯ÙÛÙ
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
        Ø§ÙØªØ®Ø§Ø¨ ÚÙØ¯ÛÙ Ø±Ú©ÙØ±Ø¯ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±
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
        """Ø¯Ø±Ø¬ Ø±Ú©ÙØ±Ø¯ Ø¬Ø¯ÛØ¯ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±"""
        def _op():
            c = self.admin if use_admin else self.client
            resp = c.table(table).insert(data).execute()
            if resp.data:
                return resp.data[0]
            raise DatabaseError("Ø±Ú©ÙØ±Ø¯ Ø¯Ø±Ø¬ ÙØ´Ø¯")

        return self._execute_with_retry(_op, f"insert({table})")

    async def update(
        self,
        table: str,
        filters: Dict[str, Any],
        data: Dict[str, Any],
        use_admin: bool = False
    ) -> List[Dict[str, Any]]:
        """Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ø±Ú©ÙØ±Ø¯ÙØ§ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±"""
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
        """Ø­Ø°Ù Ø±Ú©ÙØ±Ø¯ÙØ§ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±"""
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
        """Ø´ÙØ§Ø±Ø´ Ø±Ú©ÙØ±Ø¯ÙØ§ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±"""
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
        """Ø§Ø¬Ø±Ø§Û ØªØ§Ø¨Ø¹ RPC Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±"""
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
        """Ø¯Ø±Ø¬ ÛØ§ Ø¨ÙâØ±ÙØ²Ø±Ø³Ø§ÙÛ Ø¨Ø§ retry Ø®ÙØ¯Ú©Ø§Ø±"""
        def _op():
            c = self.admin if use_admin else self.client
            resp = c.table(table).upsert(data, on_conflict=on_conflict).execute()
            if resp.data:
                return resp.data[0]
            raise DatabaseError("upsert ÙØ§ÙÙÙÙ Ø¨ÙØ¯")

        return self._execute_with_retry(_op, f"upsert({table})")

    async def health_check(self) -> Dict[str, Any]:
        """
        Ø¨Ø±Ø±Ø³Û Ø³ÙØ§ÙØª Ú©Ø§ÙÙ Ø§ØªØµØ§Ù Ø¯ÛØªØ§Ø¨ÛØ³

        Ø®Ø±ÙØ¬Û:
            Ø¯ÛÚ©Ø´ÙØ±Û Ø­Ø§ÙÛ ÙØ¶Ø¹ÛØªØ ÙØªØ±ÛÚ©âÙØ§ Ù Ø§Ø·ÙØ§Ø¹Ø§Øª Ø§ØªØµØ§Ù
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


# ÙÙÙÙÙ Ú¯ÙÙØ¨Ø§Ù Singleton
db = SupabaseManager()


def get_db() -> SupabaseManager:
    """Ø¯Ø±ÛØ§ÙØª ÙÙÙÙÙ Ø¯ÛØªØ§Ø¨ÛØ³ â ÙÙÛØ´Ù ÙÙØ§Ù Singleton Ø±Ø§ Ø¨Ø±ÙÛâÚ¯Ø±Ø¯Ø§ÙØ¯"""
    return db
