"""backend/risk/daily_limits.py
Phase Q Fix Q-13: next_reset populated for ALL limit statuses (not only DAILY_TRADES_HIT).
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional


class LimitStatus(str, Enum):
    OK = "OK"; WARNING = "WARNING"; DAILY_TRADES_HIT = "DAILY_TRADES_HIT"
    DAILY_LOSS_HIT = "DAILY_LOSS_HIT"; WEEKLY_LOSS_HIT = "WEEKLY_LOSS_HIT"
    MONTHLY_DRAWDOWN_HIT = "MONTHLY_DRAWDOWN_HIT"


@dataclass
class TodayTrades:
    trade_count: int; pnl_usd: float; risk_used_percent: float


@dataclass
class LimitsCheckResult:
    can_trade: bool; status: LimitStatus; reason: str
    daily_trades_count: int; daily_trades_limit: int
    daily_pnl: float; daily_loss_limit_pct: float
    weekly_pnl: float; weekly_loss_limit_pct: float
    monthly_pnl: float; monthly_drawdown_limit_pct: float
    next_reset: Optional[datetime] = None  # Q-13: always set on block


def _next_midnight_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))

def _next_monday_utc() -> datetime:
    now = datetime.now(timezone.utc)
    days_to = (7 - now.weekday()) % 7 or 7
    return (now + timedelta(days=days_to)).replace(hour=0, minute=0, second=0, microsecond=0)

def _next_month_utc() -> datetime:
    now = datetime.now(timezone.utc)
    if now.month == 12: return datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    return datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)


class DailyLimitsEngine:
    def __init__(self, max_daily_trades: int = 10, max_daily_loss_pct: float = 3.0, max_weekly_loss_pct: float = 7.0, max_monthly_dd_pct: float = 15.0) -> None:
        self._max_daily_trades = max_daily_trades
        self._max_daily_loss_pct = max_daily_loss_pct
        self._max_weekly_loss_pct = max_weekly_loss_pct
        self._max_monthly_dd_pct = max_monthly_dd_pct
        self._warning_threshold = 0.80

    def check_limits(self, account_balance: float, today: TodayTrades, week_pnl_usd: float = 0.0, month_pnl_usd: float = 0.0) -> LimitsCheckResult:
        if account_balance <= 0:
            return self._blocked(LimitStatus.DAILY_LOSS_HIT, "Balance zero or negative", today, week_pnl_usd, month_pnl_usd, _next_midnight_utc())
        daily_loss_pct = (abs(min(today.pnl_usd, 0.0)) / account_balance) * 100
        week_loss_pct = (abs(min(week_pnl_usd, 0.0)) / account_balance) * 100
        month_dd_pct = (abs(min(month_pnl_usd, 0.0)) / account_balance) * 100
        base = dict(daily_trades_count=today.trade_count, daily_trades_limit=self._max_daily_trades, daily_pnl=today.pnl_usd, daily_loss_limit_pct=self._max_daily_loss_pct, weekly_pnl=week_pnl_usd, weekly_loss_limit_pct=self._max_weekly_loss_pct, monthly_pnl=month_pnl_usd, monthly_drawdown_limit_pct=self._max_monthly_dd_pct)
        if month_dd_pct >= self._max_monthly_dd_pct:
            return LimitsCheckResult(can_trade=False, status=LimitStatus.MONTHLY_DRAWDOWN_HIT, reason=f"Monthly drawdown {month_dd_pct:.2f}% >= {self._max_monthly_dd_pct}%", next_reset=_next_month_utc(), **base)
        if week_loss_pct >= self._max_weekly_loss_pct:
            return LimitsCheckResult(can_trade=False, status=LimitStatus.WEEKLY_LOSS_HIT, reason=f"Weekly loss {week_loss_pct:.2f}% >= {self._max_weekly_loss_pct}%", next_reset=_next_monday_utc(), **base)
        if daily_loss_pct >= self._max_daily_loss_pct:
            return LimitsCheckResult(can_trade=False, status=LimitStatus.DAILY_LOSS_HIT, reason=f"Daily loss {daily_loss_pct:.2f}% >= {self._max_daily_loss_pct}%", next_reset=_next_midnight_utc(), **base)
        if today.trade_count >= self._max_daily_trades:
            return LimitsCheckResult(can_trade=False, status=LimitStatus.DAILY_TRADES_HIT, reason=f"Daily trades {today.trade_count} >= {self._max_daily_trades}", next_reset=_next_midnight_utc(), **base)
        warn_reason = ""
        if daily_loss_pct >= self._max_daily_loss_pct * self._warning_threshold:
            warn_reason = f"Daily loss warning {daily_loss_pct:.2f}%"
        elif today.trade_count >= int(self._max_daily_trades * self._warning_threshold):
            warn_reason = f"Trade count warning {today.trade_count}/{self._max_daily_trades}"
        return LimitsCheckResult(can_trade=True, status=LimitStatus.WARNING if warn_reason else LimitStatus.OK, reason=warn_reason, next_reset=None, **base)

    def _blocked(self, status: LimitStatus, reason: str, today: TodayTrades, week_pnl_usd: float, month_pnl_usd: float, next_reset: Optional[datetime]) -> LimitsCheckResult:
        return LimitsCheckResult(can_trade=False, status=status, reason=reason, daily_trades_count=today.trade_count, daily_trades_limit=self._max_daily_trades, daily_pnl=today.pnl_usd, daily_loss_limit_pct=self._max_daily_loss_pct, weekly_pnl=week_pnl_usd, weekly_loss_limit_pct=self._max_weekly_loss_pct, monthly_pnl=month_pnl_usd, monthly_drawdown_limit_pct=self._max_monthly_dd_pct, next_reset=next_reset)
