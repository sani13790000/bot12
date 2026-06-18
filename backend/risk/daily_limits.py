"""
===============================================================================
Galaxy Vast AI Trading Platform
محدودیت‌های روزانه/هفتگی/ماهانه — Daily Limits Engine

این ماژول کنترل می‌کند که ربات در هر بازه زمانی چقدر ریسک می‌کند.
وقتی به حد روزانه رسید → به صورت خودکار pause می‌شود.

ویژگی‌ها:
- حداکثر معاملات در روز
- حداکثر ضرر در روز/هفته/ماه
- Auto-pause وقتی به حد رسید
- Auto-resume روز بعد

نویسنده: Galaxy Vast Team
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import List, Optional

from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("risk.daily_limits")


class LimitStatus(str, Enum):
    """وضعیت محدودیت‌های زمانی"""
    OK = "OK"                       # هیچ محدودیتی رعایت نشده
    WARNING = "WARNING"             # نزدیک به حد
    DAILY_TRADES_HIT = "DAILY_TRADES_HIT"       # حداکثر معاملات روزانه
    DAILY_LOSS_HIT = "DAILY_LOSS_HIT"           # حداکثر ضرر روزانه
    WEEKLY_LOSS_HIT = "WEEKLY_LOSS_HIT"         # حداکثر ضرر هفتگی
    MONTHLY_DRAWDOWN_HIT = "MONTHLY_DRAWDOWN_HIT"  # حداکثر drawdown ماهانه


@dataclass
class TradeRecord:
    """رکورد یک معامله برای محاسبه محدودیت‌ها"""
    symbol: str
    direction: str
    pnl: float          # سود یا ضرر (منفی = ضرر)
    closed_at: datetime
    risk_percent: float


@dataclass
class LimitsCheckResult:
    """نتیجه بررسی محدودیت‌های زمانی"""
    can_trade: bool
    status: LimitStatus
    reason: str
    daily_trades_count: int
    daily_trades_limit: int
    daily_pnl: float
    daily_loss_limit: float
    weekly_pnl: float
    weekly_loss_limit: float
    monthly_pnl: float
    monthly_drawdown_limit: float
    next_reset: Optional[datetime]


class DailyLimitsEngine:
    """
    موتور محدودیت‌های زمانی — Galaxy Vast

    این کلاس از سیستم جلوگیری می‌کند که در یک روز بد
    بیش از حد مجاز ضرر کند.

    مثال:
        engine = DailyLimitsEngine()
        result = await engine.check_limits(today_trades)
        if not result.can_trade:
            # pause ربات
    """

    def __init__(self) -> None:
        self._max_daily_trades: int = settings.MAX_DAILY_TRADES
        self._max_daily_loss_pct: float = settings.MAX_DAILY_LOSS_PERCENT
        self._max_weekly_loss_pct: float = settings.MAX_WEEKLY_LOSS_PERCENT
        self._max_monthly_drawdown_pct: float = settings.MAX_MONTHLY_DRAWDOWN_PERCENT
        self._warning_threshold: float = 0.8  # ۸۰٪ از حد مجاز → Warning
        logger.info(
            "DailyLimitsEngine راه‌اندازی شد — "
            f"حداکثر روزانه: {self._max_daily_trades} معامله | "
            f"حداکثر ضرر: {self._max_daily_loss_pct}٪"
        )

    async def check_limits(
        self,
        account_balance: float,
        closed_trades: List[TradeRecord],
    ) -> LimitsCheckResult:
        """
        بررسی همه محدودیت‌های زمانی

        ورودی:
            account_balance: موجودی فعلی حساب
            closed_trades: لیست معاملات بسته‌شده

        خروجی:
            LimitsCheckResult با وضعیت کامل
        """
        now = datetime.utcnow()
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        # فیلتر معاملات هر بازه زمانی
        daily_trades = [
            t for t in closed_trades
            if t.closed_at.date() == today
        ]
        weekly_trades = [
            t for t in closed_trades
            if t.closed_at.date() >= week_start
        ]
        monthly_trades = [
            t for t in closed_trades
            if t.closed_at.date() >= month_start
        ]

        # محاسبه PnL هر بازه
        daily_pnl = sum(t.pnl for t in daily_trades)
        weekly_pnl = sum(t.pnl for t in weekly_trades)
        monthly_pnl = sum(t.pnl for t in monthly_trades)

        # تبدیل به درصد از موجودی
        daily_loss_pct = (abs(min(0, daily_pnl)) / account_balance) * 100
        weekly_loss_pct = (abs(min(0, weekly_pnl)) / account_balance) * 100
        monthly_loss_pct = (abs(min(0, monthly_pnl)) / account_balance) * 100

        # بررسی حداکثر معاملات روزانه
        if len(daily_trades) >= self._max_daily_trades:
            next_reset = datetime.combine(today + timedelta(days=1), datetime.min.time())
            result = LimitsCheckResult(
                can_trade=False,
                status=LimitStatus.DAILY_TRADES_HIT,
                reason=f"به حداکثر معاملات روزانه ({self._max_daily_trades}) رسیدید",
                daily_trades_count=len(daily_trades),
                daily_trades_limit=self._max_daily_trades,
                daily_pnl=daily_pnl,
                daily_loss_limit=self._max_daily_loss_pct,
                weekly_pnl=weekly_pnl,
                weekly_loss_limit=self._max_weekly_loss_pct,
                monthly_pnl=monthly_pnl,
                monthly_drawdown_limit=self._max_monthly_drawdown_pct,
                next_reset=next_reset,
            )
            logger.warning(f"حد معاملات روزانه: {len(daily_trades)}/{self._max_daily_trades}")
            return result

        # بررسی حداکثر ضرر روزانه
        if daily_loss_pct >= self._max_daily_loss_pct:
            next_reset = datetime.combine(today + timedelta(days=1), datetime.min.time())
            result = LimitsCheckResult(
                can_trade=False,
                status=LimitStatus.DAILY_LOSS_HIT,
                reason=f"حداکثر ضرر روزانه ({self._max_daily_loss_pct}٪) رعایت شد",
                daily_trades_count=len(daily_trades),
                daily_trades_limit=self._max_daily_trades,
                daily_pnl=daily_pnl,
                daily_loss_limit=self._max_daily_loss_pct,
                weekly_pnl=weekly_pnl,
                weekly_loss_limit=self._max_weekly_loss_pct,
                monthly_pnl=monthly_pnl,
                monthly_drawdown_limit=self._max_monthly_drawdown_pct,
                next_reset=next_reset,
            )
            logger.warning(f"حد ضرر روزانه: {daily_loss_pct:.2f}٪/{self._max_daily_loss_pct}٪")
            return result

        # بررسی حداکثر ضرر هفتگی
        if weekly_loss_pct >= self._max_weekly_loss_pct:
            days_to_monday = (7 - today.weekday()) % 7 or 7
            next_reset = datetime.combine(today + timedelta(days=days_to_monday), datetime.min.time())
            result = LimitsCheckResult(
                can_trade=False,
                status=LimitStatus.WEEKLY_LOSS_HIT,
                reason=f"حداکثر ضرر هفتگی ({self._max_weekly_loss_pct}٪) رعایت شد",
                daily_trades_count=len(daily_trades),
                daily_trades_limit=self._max_daily_trades,
                daily_pnl=daily_pnl,
                daily_loss_limit=self._max_daily_loss_pct,
                weekly_pnl=weekly_pnl,
                weekly_loss_limit=self._max_weekly_loss_pct,
                monthly_pnl=monthly_pnl,
                monthly_drawdown_limit=self._max_monthly_drawdown_pct,
                next_reset=next_reset,
            )
            logger.warning(f"حد ضرر هفتگی: {weekly_loss_pct:.2f}٪/{self._max_weekly_loss_pct}٪")
            return result

        # بررسی حداکثر drawdown ماهانه
        if monthly_loss_pct >= self._max_monthly_drawdown_pct:
            next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
            next_reset = datetime.combine(next_month, datetime.min.time())
            result = LimitsCheckResult(
                can_trade=False,
                status=LimitStatus.MONTHLY_DRAWDOWN_HIT,
                reason=f"حداکثر drawdown ماهانه ({self._max_monthly_drawdown_pct}٪) رعایت شد",
                daily_trades_count=len(daily_trades),
                daily_trades_limit=self._max_daily_trades,
                daily_pnl=daily_pnl,
                daily_loss_limit=self._max_daily_loss_pct,
                weekly_pnl=weekly_pnl,
                weekly_loss_limit=self._max_weekly_loss_pct,
                monthly_pnl=monthly_pnl,
                monthly_drawdown_limit=self._max_monthly_drawdown_pct,
                next_reset=next_reset,
            )
            logger.warning(f"حد drawdown ماهانه: {monthly_loss_pct:.2f}٪/{self._max_monthly_drawdown_pct}٪")
            return result

        # بررسی Warning (نزدیک به حد)
        warning_reason = self._check_warnings(
            len(daily_trades), daily_loss_pct, weekly_loss_pct, monthly_loss_pct
        )

        return LimitsCheckResult(
            can_trade=True,
            status=LimitStatus.WARNING if warning_reason else LimitStatus.OK,
            reason=warning_reason or "",
            daily_trades_count=len(daily_trades),
            daily_trades_limit=self._max_daily_trades,
            daily_pnl=daily_pnl,
            daily_loss_limit=self._max_daily_loss_pct,
            weekly_pnl=weekly_pnl,
            weekly_loss_limit=self._max_weekly_loss_pct,
            monthly_pnl=monthly_pnl,
            monthly_drawdown_limit=self._max_monthly_drawdown_pct,
            next_reset=None,
        )

    def _check_warnings(
        self,
        daily_count: int,
        daily_loss: float,
        weekly_loss: float,
        monthly_loss: float,
    ) -> Optional[str]:
        """بررسی نزدیکی به حدود مجاز"""
        threshold = self._warning_threshold
        if daily_count >= int(self._max_daily_trades * threshold):
            return f"نزدیک به حد معاملات روزانه: {daily_count}/{self._max_daily_trades}"
        if daily_loss >= self._max_daily_loss_pct * threshold:
            return f"نزدیک به حد ضرر روزانه: {daily_loss:.1f}٪/{self._max_daily_loss_pct}٪"
        if weekly_loss >= self._max_weekly_loss_pct * threshold:
            return f"نزدیک به حد ضرر هفتگی: {weekly_loss:.1f}٪/{self._max_weekly_loss_pct}٪"
        return None


# نمونه singleton
daily_limits_engine = DailyLimitsEngine()
