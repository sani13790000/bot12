"""
===============================================================================
Galaxy Vast AI Trading Platform
مدیریت ریسک پرتفولیو — Portfolio Risk Manager

این ماژول مسئول کنترل ریسک کل حساب در چند نماد همزمان است.
بانک‌ها و صندوق‌های پوشش ریسک همیشه ریسک کل پرتفولیو را کنترل می‌کنند،
نه فقط ریسک هر معامله به تنهایی.

ویژگی‌ها:
- تجمیع ریسک cross-symbol در لحظه
- ماتریس همبستگی ارزها
- محدودیت exposure per currency
- بلوک خودکار معاملات جدید در صورت تجاوز از حد مجاز

نویسنده: Galaxy Vast Team
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("risk.portfolio")


# ─────────────────────────────────────────────
# ثوابت همبستگی ارزها
# جفت‌هایی که همبستگی بالا دارند → ریسک مضاعف
# ─────────────────────────────────────────────
CURRENCY_CORRELATIONS: Dict[Tuple[str, str], float] = {
    ("EURUSD", "GBPUSD"): 0.85,
    ("EURUSD", "AUDUSD"): 0.72,
    ("EURUSD", "NZDUSD"): 0.68,
    ("GBPUSD", "AUDUSD"): 0.70,
    ("USDCHF", "EURUSD"): -0.92,  # همبستگی معکوس
    ("USDCHF", "GBPUSD"): -0.88,
    ("XAUUSD", "EURUSD"): 0.45,
    ("XAUUSD", "USDCHF"): -0.55,
    ("USDJPY", "XAUUSD"): -0.40,
}


class RiskLevel(str, Enum):
    """سطوح ریسک پرتفولیو"""
    SAFE = "SAFE"           # زیر ۶۰٪ حد مجاز
    WARNING = "WARNING"     # ۶۰٪ تا ۸۰٪ حد مجاز
    CRITICAL = "CRITICAL"   # ۸۰٪ تا ۱۰۰٪ حد مجاز
    BLOCKED = "BLOCKED"     # بالای ۱۰۰٪ — معامله جدید مسدود


class TradeDirection(str, Enum):
    """جهت معامله"""
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class OpenTradeRisk:
    """اطلاعات ریسک یک معامله باز"""
    symbol: str
    direction: TradeDirection
    lot_size: float
    entry_price: float
    stop_loss: float
    account_balance: float
    risk_percent: float = field(init=False)
    risk_amount: float = field(init=False)
    base_currency: str = field(init=False)

    def __post_init__(self) -> None:
        """محاسبه خودکار درصد و مقدار ریسک"""
        pip_distance = abs(self.entry_price - self.stop_loss)
        # محاسبه ریسک دلاری بر اساس فاصله از SL و حجم لات
        if "JPY" in self.symbol:
            pip_value = self.lot_size * 1000 * pip_distance
        elif "XAU" in self.symbol:
            pip_value = self.lot_size * 100 * pip_distance
        else:
            pip_value = self.lot_size * 100000 * pip_distance * 0.0001

        self.risk_amount = pip_value
        self.risk_percent = (self.risk_amount / self.account_balance) * 100
        self.base_currency = self.symbol[:3]


@dataclass
class PortfolioRiskSnapshot:
    """وضعیت لحظه‌ای ریسک کل پرتفولیو"""
    timestamp: datetime
    total_risk_percent: float
    total_risk_amount: float
    correlation_adjusted_risk: float
    risk_level: RiskLevel
    open_trades: List[OpenTradeRisk]
    blocked_reason: Optional[str]
    currency_exposure: Dict[str, float]
    can_open_new_trade: bool
    max_allowed_risk: float
    remaining_risk_capacity: float


class PortfolioRiskManager:
    """
    مدیر ریسک پرتفولیو — Galaxy Vast

    این کلاس ریسک کل حساب را در تمام معاملات باز
    به صورت لحظه‌ای محاسبه و کنترل می‌کند.

    مثال استفاده:
        manager = PortfolioRiskManager()
        snapshot = await manager.get_portfolio_snapshot(balance, open_trades)
        if snapshot.can_open_new_trade:
            # اجازه معامله جدید
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._max_portfolio_risk: float = settings.MAX_PORTFOLIO_RISK_PERCENT
        self._max_single_currency_exposure: float = settings.MAX_SINGLE_CURRENCY_EXPOSURE
        self._correlation_multiplier: float = settings.CORRELATION_RISK_MULTIPLIER
        logger.info(
            "PortfolioRiskManager راه‌اندازی شد — "
            f"حداکثر ریسک پرتفولیو: {self._max_portfolio_risk}٪"
        )

    async def get_portfolio_snapshot(
        self,
        account_balance: float,
        open_trades: List[OpenTradeRisk],
    ) -> PortfolioRiskSnapshot:
        """
        محاسبه وضعیت کامل ریسک پرتفولیو

        ورودی:
            account_balance: موجودی فعلی حساب
            open_trades: لیست معاملات باز با اطلاعات SL

        خروجی:
            PortfolioRiskSnapshot با تمام جزئیات ریسک
        """
        async with self._lock:
            if not open_trades:
                return self._build_empty_snapshot(account_balance)

            # مرحله ۱: محاسبه ریسک خام هر معامله
            raw_total = sum(t.risk_percent for t in open_trades)

            # مرحله ۲: محاسبه تنظیم همبستگی
            correlation_bonus = self._calculate_correlation_penalty(open_trades)
            adjusted_risk = raw_total + correlation_bonus

            # مرحله ۳: محاسبه exposure per currency
            currency_exposure = self._calculate_currency_exposure(open_trades)

            # مرحله ۴: تعیین سطح ریسک
            risk_level, blocked_reason = self._determine_risk_level(
                adjusted_risk, currency_exposure
            )

            can_open = risk_level not in (RiskLevel.BLOCKED,)
            remaining = max(0.0, self._max_portfolio_risk - adjusted_risk)

            snapshot = PortfolioRiskSnapshot(
                timestamp=datetime.utcnow(),
                total_risk_percent=raw_total,
                total_risk_amount=sum(t.risk_amount for t in open_trades),
                correlation_adjusted_risk=adjusted_risk,
                risk_level=risk_level,
                open_trades=open_trades,
                blocked_reason=blocked_reason,
                currency_exposure=currency_exposure,
                can_open_new_trade=can_open,
                max_allowed_risk=self._max_portfolio_risk,
                remaining_risk_capacity=remaining,
            )

            logger.info(
                f"پرتفولیو snapshot — "
                f"ریسک خام: {raw_total:.2f}٪ | "
                f"تنظیم‌شده: {adjusted_risk:.2f}٪ | "
                f"سطح: {risk_level.value} | "
                f"باقی‌مانده: {remaining:.2f}٪"
            )
            return snapshot

    async def can_add_trade(
        self,
        new_trade: OpenTradeRisk,
        existing_trades: List[OpenTradeRisk],
    ) -> Tuple[bool, str]:
        """
        بررسی امکان افزودن معامله جدید به پرتفولیو

        خروجی:
            (True, "") → مجاز
            (False, "دلیل") → مسدود
        """
        all_trades = existing_trades + [new_trade]
        snapshot = await self.get_portfolio_snapshot(
            new_trade.account_balance, all_trades
        )

        if not snapshot.can_open_new_trade:
            return False, snapshot.blocked_reason or "ریسک پرتفولیو از حد مجاز بیشتر است"

        # بررسی exposure ارز جدید
        new_currency = new_trade.base_currency
        current_exposure = snapshot.currency_exposure.get(new_currency, 0.0)
        if current_exposure > self._max_single_currency_exposure:
            return False, (
                f"exposure ارز {new_currency} "
                f"({current_exposure:.1f}٪) از حد مجاز "
                f"({self._max_single_currency_exposure}٪) بیشتر است"
            )

        return True, ""

    def _calculate_correlation_penalty(
        self, trades: List[OpenTradeRisk]
    ) -> float:
        """
        محاسبه جریمه همبستگی

        وقتی دو ارز همبستگی بالا دارند و هر دو در یک جهت باز هستند،
        ریسک واقعی بیشتر از مجموع ریسک‌های جداگانه است.
        """
        penalty = 0.0
        symbols = [t.symbol for t in trades]

        for i in range(len(trades)):
            for j in range(i + 1, len(trades)):
                pair = (trades[i].symbol, trades[j].symbol)
                reverse_pair = (trades[j].symbol, trades[i].symbol)

                correlation = CURRENCY_CORRELATIONS.get(
                    pair, CURRENCY_CORRELATIONS.get(reverse_pair, 0.0)
                )

                if abs(correlation) < 0.5:
                    continue

                # همبستگی مثبت + یک جهت → جریمه بیشتر
                same_direction = trades[i].direction == trades[j].direction
                if correlation > 0 and same_direction:
                    combined_risk = (trades[i].risk_percent + trades[j].risk_percent)
                    penalty += combined_risk * correlation * self._correlation_multiplier
                # همبستگی منفی + یک جهت → پوشش ریسک → کاهش
                elif correlation < 0 and same_direction:
                    combined_risk = (trades[i].risk_percent + trades[j].risk_percent)
                    penalty -= combined_risk * abs(correlation) * 0.3

        return max(0.0, penalty)

    def _calculate_currency_exposure(
        self, trades: List[OpenTradeRisk]
    ) -> Dict[str, float]:
        """محاسبه exposure هر ارز پایه"""
        exposure: Dict[str, float] = {}
        for trade in trades:
            base = trade.base_currency
            exposure[base] = exposure.get(base, 0.0) + trade.risk_percent
        return exposure

    def _determine_risk_level(
        self,
        adjusted_risk: float,
        currency_exposure: Dict[str, float],
    ) -> Tuple[RiskLevel, Optional[str]]:
        """تعیین سطح ریسک و دلیل مسدود شدن"""
        # بررسی ریسک کل
        ratio = adjusted_risk / self._max_portfolio_risk if self._max_portfolio_risk > 0 else 0

        if ratio >= 1.0:
            return RiskLevel.BLOCKED, (
                f"ریسک پرتفولیو ({adjusted_risk:.2f}٪) از حد مجاز "
                f"({self._max_portfolio_risk}٪) فراتر رفته است"
            )

        # بررسی exposure هر ارز
        for currency, exposure in currency_exposure.items():
            if exposure > self._max_single_currency_exposure:
                return RiskLevel.BLOCKED, (
                    f"exposure ارز {currency} ({exposure:.2f}٪) "
                    f"از حد مجاز ({self._max_single_currency_exposure}٪) بیشتر است"
                )

        if ratio >= 0.8:
            return RiskLevel.CRITICAL, None
        if ratio >= 0.6:
            return RiskLevel.WARNING, None
        return RiskLevel.SAFE, None

    def _build_empty_snapshot(self, balance: float) -> PortfolioRiskSnapshot:
        """ساخت snapshot خالی برای حساب بدون معامله باز"""
        return PortfolioRiskSnapshot(
            timestamp=datetime.utcnow(),
            total_risk_percent=0.0,
            total_risk_amount=0.0,
            correlation_adjusted_risk=0.0,
            risk_level=RiskLevel.SAFE,
            open_trades=[],
            blocked_reason=None,
            currency_exposure={},
            can_open_new_trade=True,
            max_allowed_risk=self._max_portfolio_risk,
            remaining_risk_capacity=self._max_portfolio_risk,
        )


# نمونه singleton برای استفاده در سراسر برنامه
portfolio_risk_manager = PortfolioRiskManager()
