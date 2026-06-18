"""
=====================================================================
فایل: backend/services/session_alert_service.py

توضیح:
    این سرویس هشدارهای باز/پایان سشن را به صورت خودکار از طریق
    Python Scheduler ارسال می‌کند.

    مشکل قبلی: SessionManager.mqh در MQL5 هیچ webhook به Python نمی‌زد.
    راه‌حل: Python Scheduler هر دقیقه سشن را چک می‌کند و هشدار می‌دهد.

    جریان کار:
        1. Scheduler هر ۶۰ ثانیه متد check_and_alert() را صدا می‌زند
        2. سشن فعلی با سشن قبلی مقایسه می‌شود
        3. اگر سشن جدید باز شد → send_session_open_alert()
        4. اگر سشن قبلی بسته شد → send_session_close_alert()
        5. اگر Kill Zone فعال شد → send_kill_zone_alert()

نویسنده: MT5 Trading Team
نسخه: 1.0.0
=====================================================================
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Set
from dataclasses import dataclass

from .session_service import SessionService, SessionInfo, SessionType, KillZoneType
from ..core.logger import get_logger

logger = get_logger("session_alert_service")


@dataclass
class SessionAlertState:
    """وضعیت فعلی هشدارهای سشن برای جلوگیری از ارسال تکراری"""
    active_sessions: Set[str]
    active_kill_zones: Set[str]
    last_check: Optional[datetime]

    def __init__(self):
        self.active_sessions = set()
        self.active_kill_zones = set()
        self.last_check = None


# ─── نوع تابع callback برای ارسال هشدار ───
# این callback از bot.py تنظیم می‌شود تا وابستگی دوطرفه نباشد
_alert_callback = None


def set_alert_callback(callback):
    """
    تنظیم callback برای ارسال هشدار

    Args:
        callback: تابع async که پیام و نوع هشدار دریافت می‌کند
                  signature: async def callback(alert_type: str, data: dict) -> None
    """
    global _alert_callback
    _alert_callback = callback
    logger.info("✅ Alert callback برای session_alert_service تنظیم شد")


class SessionAlertService:
    """
    سرویس هشدار خودکار سشن‌های معاملاتی

    این کلاس به صورت مستقل در یک asyncio task اجرا می‌شود و
    تغییرات سشن را رصد می‌کند.
    """

    def __init__(self, check_interval_seconds: int = 60):
        """
        مقداردهی اولیه

        Args:
            check_interval_seconds: فاصله زمانی بین هر چک (پیش‌فرض ۶۰ ثانیه)
        """
        self._session_service = SessionService()
        self._state = SessionAlertState()
        self._check_interval = check_interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        logger.info(f"SessionAlertService راه‌اندازی شد — بازه چک: {check_interval_seconds}s")

    async def start(self):
        """شروع scheduler در background"""
        if self._running:
            logger.warning("SessionAlertService قبلاً در حال اجراست")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("✅ SessionAlertService شروع به کار کرد")

    async def stop(self):
        """توقف scheduler"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🛑 SessionAlertService متوقف شد")

    async def _run_loop(self):
        """حلقه اصلی چک سشن"""
        while self._running:
            try:
                await self.check_and_alert()
            except Exception as e:
                logger.error(f"خطا در چک سشن: {e}", exc_info=True)
            await asyncio.sleep(self._check_interval)

    async def check_and_alert(self):
        """
        چک وضعیت سشن و ارسال هشدار در صورت تغییر

        این متد هر ۶۰ ثانیه صدا زده می‌شود و:
        - سشن‌های جدید را شناسایی می‌کند
        - سشن‌های بسته شده را شناسایی می‌کند
        - Kill Zone های جدید را شناسایی می‌کند
        """
        now = datetime.now(timezone.utc)
        session_info = self._session_service.get_current_session()

        # مجموعه سشن‌های فعلی
        current_sessions: Set[str] = set(session_info.active_sessions) if session_info.active_sessions else set()
        current_kill_zones: Set[str] = set()
        if session_info.is_kill_zone and session_info.kill_zone != KillZoneType.NONE:
            current_kill_zones.add(session_info.kill_zone.value)

        # ─── هشدار باز شدن سشن جدید ───
        newly_opened = current_sessions - self._state.active_sessions
        for session_name in newly_opened:
            logger.info(f"📢 سشن جدید باز شد: {session_name}")
            await self._send_alert("SESSION_OPEN", {
                "session_name": session_name,
                "session_type": session_info.session_type.value,
                "kill_zone": session_info.kill_zone.value,
                "is_overlap": session_info.is_overlap,
                "can_trade": session_info.can_trade,
                "session_score": session_info.session_score,
                "utc_time": now.strftime("%H:%M UTC"),
                "minutes_to_london": session_info.minutes_to_london_open,
                "minutes_to_ny": session_info.minutes_to_ny_open
            })

        # ─── هشدار بسته شدن سشن ───
        newly_closed = self._state.active_sessions - current_sessions
        for session_name in newly_closed:
            logger.info(f"🔔 سشن بسته شد: {session_name}")
            await self._send_alert("SESSION_CLOSE", {
                "session_name": session_name,
                "utc_time": now.strftime("%H:%M UTC"),
                "remaining_sessions": list(current_sessions)
            })

        # ─── هشدار فعال شدن Kill Zone ───
        newly_active_kz = current_kill_zones - self._state.active_kill_zones
        for kz_name in newly_active_kz:
            logger.info(f"🎯 Kill Zone فعال شد: {kz_name}")
            await self._send_alert("KILL_ZONE_OPEN", {
                "kill_zone_name": kz_name,
                "session_type": session_info.session_type.value,
                "session_score": session_info.session_score,
                "can_trade": session_info.can_trade,
                "utc_time": now.strftime("%H:%M UTC")
            })

        # ─── هشدار پایان Kill Zone ───
        newly_closed_kz = self._state.active_kill_zones - current_kill_zones
        for kz_name in newly_closed_kz:
            logger.info(f"⏰ Kill Zone پایان یافت: {kz_name}")
            await self._send_alert("KILL_ZONE_CLOSE", {
                "kill_zone_name": kz_name,
                "utc_time": now.strftime("%H:%M UTC")
            })

        # ─── بروزرسانی state ───
        self._state.active_sessions = current_sessions
        self._state.active_kill_zones = current_kill_zones
        self._state.last_check = now

    async def _send_alert(self, alert_type: str, data: dict):
        """
        ارسال هشدار از طریق callback تنظیم‌شده

        Args:
            alert_type: نوع هشدار: SESSION_OPEN, SESSION_CLOSE, KILL_ZONE_OPEN, KILL_ZONE_CLOSE
            data: داده‌های هشدار
        """
        if _alert_callback is None:
            logger.warning(f"Alert callback تنظیم نشده — هشدار {alert_type} ارسال نشد")
            return
        try:
            await _alert_callback(alert_type, data)
        except Exception as e:
            logger.error(f"خطا در ارسال هشدار {alert_type}: {e}", exc_info=True)

    def get_status(self) -> dict:
        """وضعیت فعلی سرویس"""
        return {
            "running": self._running,
            "check_interval_seconds": self._check_interval,
            "active_sessions": list(self._state.active_sessions),
            "active_kill_zones": list(self._state.active_kill_zones),
            "last_check": self._state.last_check.isoformat() if self._state.last_check else None
        }


# ─── singleton ───
session_alert_service = SessionAlertService(check_interval_seconds=60)
