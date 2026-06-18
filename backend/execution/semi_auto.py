"""
===============================================================================
Galaxy Vast AI Trading Platform
حالت نیمه‌خودکار — Semi-Auto Execution Mode

در این حالت ربات سیگنال تولید می‌کند اما قبل از اجرا
منتظر تأیید کاربر از طریق تلگرام می‌ماند.

جریان کار:
    ۱. ربات سیگنال تولید می‌کند
    ۲. پیام به تلگرام ارسال می‌شود: "تأیید می‌کنید؟ ✅/❌"
    ۳. کاربر ✅ می‌زند → معامله اجرا می‌شود
    ۴. کاربر ❌ می‌زند → معامله لغو می‌شود
    ۵. بعد از timeout → معامله خودکار لغو می‌شود

نویسنده: Galaxy Vast Team
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, Optional

from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("execution.semi_auto")


class PendingSignalStatus(str, Enum):
    """وضعیت سیگنال در انتظار تأیید"""
    WAITING = "WAITING"         # در انتظار تأیید کاربر
    APPROVED = "APPROVED"       # تأیید شد → در صف اجرا
    REJECTED = "REJECTED"       # رد شد توسط کاربر
    EXPIRED = "EXPIRED"         # منقضی شد (timeout)
    EXECUTED = "EXECUTED"       # اجرا شد


@dataclass
class PendingSignal:
    """سیگنال در انتظار تأیید"""
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = ""
    action: str = ""            # BUY یا SELL
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    lot_size: float = 0.0
    risk_percent: float = 0.0
    confidence_score: float = 0.0
    rr_ratio: float = 0.0
    market_context: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(init=False)
    status: PendingSignalStatus = PendingSignalStatus.WAITING
    approved_by: Optional[int] = None      # Telegram user_id
    approved_at: Optional[datetime] = None
    message_id: Optional[int] = None       # پیام تلگرام برای ویرایش

    def __post_init__(self) -> None:
        timeout_seconds = settings.SEMI_AUTO_CONFIRMATION_TIMEOUT_SECONDS
        self.expires_at = self.created_at + timedelta(seconds=timeout_seconds)

    @property
    def is_expired(self) -> bool:
        """بررسی انقضای سیگنال"""
        return datetime.utcnow() > self.expires_at

    @property
    def remaining_seconds(self) -> int:
        """ثانیه‌های باقی‌مانده تا انقضا"""
        remaining = (self.expires_at - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))


class SemiAutoManager:
    """
    مدیر حالت نیمه‌خودکار — Galaxy Vast

    این کلاس سیگنال‌ها را در صف نگه می‌دارد تا
    کاربر از طریق تلگرام آنها را تأیید یا رد کند.

    مثال:
        manager = SemiAutoManager()
        signal_id = await manager.submit_for_approval(signal, on_approved_cb)
        # کاربر در تلگرام ✅ می‌زند
        result = await manager.approve_signal(signal_id, user_id)
    """

    def __init__(self) -> None:
        self._pending: Dict[str, PendingSignal] = {}
        self._lock = asyncio.Lock()
        self._on_approved_callbacks: Dict[str, Callable] = {}
        self._on_rejected_callbacks: Dict[str, Callable] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        logger.info("SemiAutoManager راه‌اندازی شد")

    async def start(self) -> None:
        """راه‌اندازی cleanup task برای سیگنال‌های منقضی"""
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_loop())
        logger.info("SemiAutoManager cleanup loop شروع شد")

    async def stop(self) -> None:
        """توقف cleanup task"""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("SemiAutoManager متوقف شد")

    async def submit_for_approval(
        self,
        signal: PendingSignal,
        on_approved: Optional[Callable] = None,
        on_rejected: Optional[Callable] = None,
    ) -> str:
        """
        ارسال سیگنال برای تأیید کاربر

        ورودی:
            signal: سیگنال برای تأیید
            on_approved: callback وقتی تأیید شد
            on_rejected: callback وقتی رد شد

        خروجی:
            signal_id برای ردیابی
        """
        async with self._lock:
            self._pending[signal.signal_id] = signal
            if on_approved:
                self._on_approved_callbacks[signal.signal_id] = on_approved
            if on_rejected:
                self._on_rejected_callbacks[signal.signal_id] = on_rejected

        logger.info(
            f"سیگنال {signal.signal_id[:8]} در انتظار تأیید — "
            f"{signal.symbol} {signal.action} | "
            f"timeout: {signal.remaining_seconds} ثانیه"
        )
        return signal.signal_id

    async def approve_signal(
        self, signal_id: str, approved_by_user_id: int
    ) -> Optional[PendingSignal]:
        """
        تأیید سیگنال توسط کاربر

        خروجی:
            PendingSignal تأیید‌شده یا None اگر منقضی/پیدا نشد
        """
        async with self._lock:
            signal = self._pending.get(signal_id)
            if not signal:
                logger.warning(f"سیگنال {signal_id[:8]} پیدا نشد")
                return None

            if signal.is_expired:
                signal.status = PendingSignalStatus.EXPIRED
                logger.warning(f"سیگنال {signal_id[:8]} منقضی شده است")
                return None

            if signal.status != PendingSignalStatus.WAITING:
                logger.warning(f"سیگنال {signal_id[:8]} وضعیت نامعتبر: {signal.status}")
                return None

            signal.status = PendingSignalStatus.APPROVED
            signal.approved_by = approved_by_user_id
            signal.approved_at = datetime.utcnow()

        logger.info(
            f"✅ سیگنال {signal_id[:8]} تأیید شد توسط کاربر {approved_by_user_id}"
        )

        # اجرای callback
        callback = self._on_approved_callbacks.get(signal_id)
        if callback:
            asyncio.create_task(callback(signal))

        return signal

    async def reject_signal(
        self, signal_id: str, rejected_by_user_id: int
    ) -> Optional[PendingSignal]:
        """
        رد سیگنال توسط کاربر

        خروجی:
            PendingSignal رد‌شده یا None
        """
        async with self._lock:
            signal = self._pending.get(signal_id)
            if not signal:
                return None

            if signal.status != PendingSignalStatus.WAITING:
                return None

            signal.status = PendingSignalStatus.REJECTED

        logger.info(
            f"❌ سیگنال {signal_id[:8]} رد شد توسط کاربر {rejected_by_user_id}"
        )

        callback = self._on_rejected_callbacks.get(signal_id)
        if callback:
            asyncio.create_task(callback(signal))

        return signal

    async def get_pending_signals(self) -> list:
        """دریافت لیست سیگنال‌های در انتظار تأیید"""
        async with self._lock:
            return [
                s for s in self._pending.values()
                if s.status == PendingSignalStatus.WAITING and not s.is_expired
            ]

    async def get_signal(self, signal_id: str) -> Optional[PendingSignal]:
        """دریافت اطلاعات یک سیگنال"""
        async with self._lock:
            return self._pending.get(signal_id)

    async def _cleanup_expired_loop(self) -> None:
        """پاکسازی خودکار سیگنال‌های منقضی هر ۳۰ ثانیه"""
        while True:
            try:
                await asyncio.sleep(30)
                await self._expire_old_signals()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"خطا در cleanup loop: {exc}")

    async def _expire_old_signals(self) -> None:
        """منقضی کردن سیگنال‌های timeout شده"""
        async with self._lock:
            expired_ids = [
                sid for sid, sig in self._pending.items()
                if sig.status == PendingSignalStatus.WAITING and sig.is_expired
            ]

        for sid in expired_ids:
            async with self._lock:
                signal = self._pending.get(sid)
                if signal:
                    signal.status = PendingSignalStatus.EXPIRED

            callback = self._on_rejected_callbacks.get(sid)
            if callback:
                signal = self._pending.get(sid)
                if signal:
                    asyncio.create_task(callback(signal))

            logger.info(f"⏰ سیگنال {sid[:8]} منقضی شد")


# نمونه singleton
semi_auto_manager = SemiAutoManager()
