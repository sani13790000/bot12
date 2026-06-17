"""
سرویس Audit و لاگ عملیات

ثبت و مدیریت لاگ عملیات حساس برای امنیت و ردیابی.

نویسنده: MT5 Trading Team
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum

from ..core.logger import get_logger
from ..database import db

logger = get_logger("audit")


class AuditAction(str, Enum):
    """انواع عملیات قابل کشیدن لاگ"""
    # احراز هویت
    LOGIN = "login"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"

    # لایسنس
    LICENSE_VALIDATE = "license_validate"
    LICENSE_ACTIVATE = "license_activate"
    LICENSE_REVOKE = "license_revoke"

    # تحلیل
    ANALYSIS_REQUEST = "analysis_request"
    DECISION_REQUEST = "decision_request"

    # معاملات
    TRADE_OPEN = "trade_open"
    TRADE_CLOSE = "trade_close"
    SIGNAL_GENERATE = "signal_generate"

    # مدیریت
    SETTINGS_CHANGE = "settings_change"
    USER_UPDATE = "user_update"


class AuditService:
    """
    سرویس ثبت عملیات

    مسئول ثبت و مدیریت لاگ عملیات حساس
    """

    def __init__(self):
        self._buffer: List[Dict[str, Any]] = []
        self._buffer_size = 50

    async def log(
        self,
        action: AuditAction,
        user_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """
        ثبت عملیات

        Args:
            action: نوع عملیات
            user_id: شناسه کاربر
            resource_type: نوع منبع
            resource_id: شناسه منبع
            details: جزئیات
            ip_address: آدرس IP
            user_agent: User Agent
            success: موفقیت عملیات
            error_message: پیام خطا در صورت عدم موفقیت
        """
        log_entry = {
            "action": action.value,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
            "ip_address": ip_address,
            "user_agent": user_agent,
            "success": success,
            "error_message": error_message,
            "created_at": datetime.utcnow().isoformat()
        }

        # لاگ محلی
        status = "موفق" if success else "ناموفق"
        logger.info(
            f"AUDIT: {action.value} - کاربر: {user_id or 'ناشناس'} - "
            f"منبع: {resource_type or '-'}/{resource_id or '-'} - {status}"
        )

        # ذخیره در دیتابیس
        try:
            await db.insert("activity_logs", log_entry, use_admin=True)
        except Exception as e:
            logger.error(f"خطا در ثبت لاگ عملیات: {e}")
            # ذخیره در بافر برای ارسال بعدی
            self._buffer.append(log_entry)
            if len(self._buffer) >= self._buffer_size:
                await self._flush_buffer()

    async def log_login(
        self,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ) -> None:
        """ثبت ورود"""
        await self.log(
            action=AuditAction.LOGIN,
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=error_message
        )

    async def log_decision(
        self,
        user_id: str,
        symbol: str,
        decision: str,
        score: int,
        ip_address: Optional[str] = None
    ) -> None:
        """ثبت درخواست تصمیم"""
        await self.log(
            action=AuditAction.DECISION_REQUEST,
            user_id=user_id,
            resource_type="symbol",
            resource_id=symbol,
            details={
                "decision": decision,
                "score": score
            },
            ip_address=ip_address
        )

    async def log_signal(
        self,
        user_id: str,
        signal_id: str,
        symbol: str,
        direction: str,
        ip_address: Optional[str] = None
    ) -> None:
        """ثبت تولید سیگنال"""
        await self.log(
            action=AuditAction.SIGNAL_GENERATE,
            user_id=user_id,
            resource_type="signal",
            resource_id=signal_id,
            details={
                "symbol": symbol,
                "direction": direction
            },
            ip_address=ip_address
        )

    async def log_trade(
        self,
        user_id: str,
        trade_id: str,
        action: str,
        symbol: str,
        direction: str,
        profit: Optional[float] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """ثبت عملیات معاملاتی"""
        audit_action = AuditAction.TRADE_OPEN if action == "open" else AuditAction.TRADE_CLOSE
        details = {
            "symbol": symbol,
            "direction": direction,
            "action": action
        }
        if profit is not None:
            details["profit"] = profit

        await self.log(
            action=audit_action,
            user_id=user_id,
            resource_type="trade",
            resource_id=trade_id,
            details=details,
            ip_address=ip_address
        )

    async def log_license(
        self,
        action: AuditAction,
        license_key: str,
        user_id: Optional[str] = None,
        device_id: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """ثبت عملیات لایسنس"""
        details = {"license_key": license_key[:12] + "****"}
        if device_id:
            details["device_id"] = device_id

        await self.log(
            action=action,
            user_id=user_id,
            resource_type="license",
            resource_id=license_key,
            details=details,
            success=success,
            error_message=error_message,
            ip_address=ip_address
        )

    async def get_user_logs(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        دریافت لاگ‌های کاربر

        Args:
            user_id: شناسه کاربر
            limit: حداکثر تعداد
            offset: از چه رکوردی

        Returns:
            لیست لاگ‌ها
        """
        return await db.select_many(
            "activity_logs",
            filters={"user_id": user_id},
            order_by="created_at",
            order_desc=True,
            limit=limit,
            offset=offset,
            use_admin=True
        )

    async def get_action_logs(
        self,
        action: AuditAction,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        دریافت لاگ‌های یک نوع عملیات

        Args:
            action: نوع عملیات
            limit: حداکثر تعداد
            offset: از چه رکوردی

        Returns:
            لیست لاگ‌ها
        """
        logs = await db.select_many(
            "activity_logs",
            order_by="created_at",
            order_desc=True,
            limit=limit,
            offset=offset,
            use_admin=True
        )

        return [l for l in logs if l.get("action") == action.value]

    async def _flush_buffer(self) -> None:
        """ارسال بافر به دیتابیس"""
        if not self._buffer:
            return

        try:
            for entry in self._buffer:
                await db.insert("activity_logs", entry, use_admin=True)
            self._buffer.clear()
            logger.debug("بافر لاگ عملیات پاک شد")
        except Exception as e:
            logger.error(f"خطا در ارسال بافر لاگ: {e}")


# نمونه گلوبال
audit_service = AuditService()
