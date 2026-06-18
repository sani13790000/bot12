"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: TradeMemory — حافظه معاملاتی

وظیفه:
  هر معامله با تمام context ورود، شرایط بازار،
  وضعیت سشن، ولاتیلیتی و خروجی نهایی ذخیره می‌شود.
  این داده پایه یادگیری ML و Failure Analysis است.

قانون اصلی:
  زیان ≠ اشتباه
  اشتباه = نقض قوانین سیستم یا ورود در شرایط نامعتبر
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("intelligence.trade_memory")


class TradeOutcome(str, Enum):
    """نتیجه نهایی معامله"""
    WIN = "WIN"           # معامله سودده
    LOSS = "LOSS"         # معامله زیان‌ده
    BREAKEVEN = "BE"      # معامله سربه‌سر
    PARTIAL = "PARTIAL"   # بسته‌شدن جزئی


class MarketSession(str, Enum):
    """سشن فعال هنگام ورود"""
    ASIAN = "ASIAN"
    LONDON = "LONDON"
    NEW_YORK = "NEW_YORK"
    LONDON_NY_OVERLAP = "LONDON_NY_OVERLAP"
    OFF_HOURS = "OFF_HOURS"


class MarketCondition(str, Enum):
    """وضعیت کلی بازار هنگام ورود"""
    TRENDING_BULLISH = "TRENDING_BULLISH"
    TRENDING_BEARISH = "TRENDING_BEARISH"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    POST_NEWS = "POST_NEWS"


@dataclass
class SMCContext:
    """
    Context کامل SMC هنگام ورود معامله.
    تمام مقادیر امتیاز بین ۰.۰ تا ۱.۰ هستند.
    """
    bos_detected: bool = False           # آیا BOS تشخیص داده شد
    choch_detected: bool = False         # آیا CHOCH تشخیص داده شد
    order_block_quality: float = 0.0     # کیفیت Order Block (0-1)
    fvg_quality: float = 0.0             # کیفیت FVG (0-1)
    liquidity_swept: bool = False        # آیا liquidity جاروب شد
    in_premium_zone: bool = False        # قیمت در Premium Zone
    in_discount_zone: bool = False       # قیمت در Discount Zone
    kill_zone_active: bool = False       # آیا Kill Zone فعال بود
    structure_score: float = 0.0         # امتیاز کلی ساختار (0-1)
    htf_alignment: float = 0.0           # هم‌راستایی با HTF (0-1)


@dataclass
class PAContext:
    """
    Context کامل Price Action هنگام ورود.
    """
    primary_pattern: str = ""            # الگوی اصلی (Pin Bar, Engulfing, ...)
    pattern_quality: float = 0.0         # کیفیت الگو (0-1)
    confirmation_patterns: List[str] = field(default_factory=list)  # الگوهای تأییدکننده
    rejection_strength: float = 0.0      # قدرت رد شدن قیمت (0-1)
    momentum_alignment: bool = False     # هم‌راستایی با مومنتوم


@dataclass
class RiskContext:
    """
    اطلاعات ریسک هنگام ورود معامله.
    """
    lot_size: float = 0.0                # حجم لات
    risk_percent: float = 0.0            # درصد ریسک از موجودی
    stop_loss_pips: float = 0.0          # فاصله SL به پیپ
    take_profit_pips: float = 0.0        # فاصله TP به پیپ
    risk_reward_ratio: float = 0.0       # نسبت R:R
    portfolio_risk_at_entry: float = 0.0 # ریسک کل پرتفولیو هنگام ورود
    atr_at_entry: float = 0.0            # مقدار ATR هنگام ورود
    spread_at_entry: float = 0.0         # اسپرد هنگام ورود


@dataclass
class TradeContext:
    """
    Context کامل یک معامله — از ورود تا خروج.
    این ساختار پایه یادگیری ML است.
    """
    # شناسه‌ها
    trade_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str = ""
    symbol: str = ""

    # زمان‌بندی
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    duration_minutes: float = 0.0

    # قیمت‌ها
    entry_price: float = 0.0
    exit_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    direction: str = ""  # BUY / SELL

    # نتیجه
    outcome: TradeOutcome = TradeOutcome.LOSS
    pnl_pips: float = 0.0
    pnl_usd: float = 0.0
    realized_rr: float = 0.0            # R:R واقعی محقق‌شده

    # context ورود
    confidence_score: float = 0.0       # امتیاز اطمینان Decision Engine
    session: MarketSession = MarketSession.OFF_HOURS
    market_condition: MarketCondition = MarketCondition.RANGING

    # context تحلیل
    smc: SMCContext = field(default_factory=SMCContext)
    price_action: PAContext = field(default_factory=PAContext)
    risk: RiskContext = field(default_factory=RiskContext)

    # اطلاعات تکمیلی
    news_active: bool = False            # آیا خبر مهم فعال بود
    previous_consecutive_losses: int = 0 # تعداد زیان‌های متوالی قبل
    notes: str = ""                      # یادداشت‌های اضافی

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به dictionary برای ذخیره در دیتابیس"""
        data = asdict(self)
        # تبدیل datetime به string
        if self.entry_time:
            data["entry_time"] = self.entry_time.isoformat()
        if self.exit_time:
            data["exit_time"] = self.exit_time.isoformat()
        return data

    def to_ml_features(self) -> Dict[str, float]:
        """
        استخراج feature vector برای مدل‌های ML.
        تمام مقادیر عددی normalize شده برای XGBoost/LightGBM.
        """
        session_map = {
            MarketSession.ASIAN: 0,
            MarketSession.LONDON: 1,
            MarketSession.NEW_YORK: 2,
            MarketSession.LONDON_NY_OVERLAP: 3,
            MarketSession.OFF_HOURS: 4,
        }
        condition_map = {
            MarketCondition.TRENDING_BULLISH: 0,
            MarketCondition.TRENDING_BEARISH: 1,
            MarketCondition.RANGING: 2,
            MarketCondition.HIGH_VOLATILITY: 3,
            MarketCondition.LOW_VOLATILITY: 4,
            MarketCondition.POST_NEWS: 5,
        }
        return {
            # SMC features
            "bos_detected": float(self.smc.bos_detected),
            "choch_detected": float(self.smc.choch_detected),
            "order_block_quality": self.smc.order_block_quality,
            "fvg_quality": self.smc.fvg_quality,
            "liquidity_swept": float(self.smc.liquidity_swept),
            "in_premium_zone": float(self.smc.in_premium_zone),
            "in_discount_zone": float(self.smc.in_discount_zone),
            "kill_zone_active": float(self.smc.kill_zone_active),
            "structure_score": self.smc.structure_score,
            "htf_alignment": self.smc.htf_alignment,

            # Price Action features
            "pattern_quality": self.price_action.pattern_quality,
            "rejection_strength": self.price_action.rejection_strength,
            "momentum_alignment": float(self.price_action.momentum_alignment),
            "num_confirmation_patterns": float(len(self.price_action.confirmation_patterns)),

            # Risk features
            "risk_percent": self.risk.risk_percent,
            "risk_reward_ratio": self.risk.risk_reward_ratio,
            "portfolio_risk_at_entry": self.risk.portfolio_risk_at_entry,
            "atr_normalized": self.risk.atr_at_entry / max(self.entry_price, 1e-9),
            "spread_normalized": self.risk.spread_at_entry / max(self.risk.atr_at_entry, 1e-9),

            # Market context
            "confidence_score": self.confidence_score / 100.0,
            "session": float(session_map.get(self.session, 4)),
            "market_condition": float(condition_map.get(self.market_condition, 2)),
            "news_active": float(self.news_active),
            "previous_consecutive_losses": float(min(self.previous_consecutive_losses, 10)),
            "duration_minutes": min(self.duration_minutes / 1440.0, 1.0),  # normalize به روز
        }


class TradeMemory:
    """
    حافظه معاملاتی Galaxy Vast.

    وظیفه:
      ذخیره، بازیابی و آنالیز context تمام معاملات.
      پایه یادگیری ML و Failure Analysis.
    """

    def __init__(self, max_memory: int = 10_000) -> None:
        """
        Args:
            max_memory: حداکثر تعداد معاملات در حافظه RAM.
                       معاملات قدیمی‌تر به دیتابیس منتقل می‌شوند.
        """
        self._max_memory = max_memory
        self._memory: List[TradeContext] = []
        logger.info(f"TradeMemory راه‌اندازی شد — ظرفیت: {max_memory} معامله")

    def record(self, context: TradeContext) -> None:
        """
        ثبت یک معامله جدید در حافظه.

        Args:
            context: context کامل معامله
        """
        self._memory.append(context)
        if len(self._memory) > self._max_memory:
            # حذف قدیمی‌ترین معامله برای آزاد کردن RAM
            removed = self._memory.pop(0)
            logger.debug(f"معامله قدیمی از RAM حذف شد: {removed.trade_id}")

        logger.info(
            f"معامله ثبت شد | {context.symbol} | {context.direction} | "
            f"{context.outcome.value} | PnL: {context.pnl_pips:+.1f} پیپ"
        )

    def get_all(self) -> List[TradeContext]:
        """برگرداندن تمام معاملات در حافظه"""
        return list(self._memory)

    def get_by_symbol(self, symbol: str) -> List[TradeContext]:
        """فیلتر معاملات بر اساس نماد"""
        return [t for t in self._memory if t.symbol == symbol]

    def get_by_outcome(self, outcome: TradeOutcome) -> List[TradeContext]:
        """فیلتر معاملات بر اساس نتیجه"""
        return [t for t in self._memory if t.outcome == outcome]

    def get_recent(self, n: int = 100) -> List[TradeContext]:
        """برگرداندن n معامله اخیر"""
        return self._memory[-n:]

    def get_win_rate(self, symbol: Optional[str] = None) -> float:
        """
        محاسبه نرخ برنده.

        Args:
            symbol: اگر None باشد، برای همه نمادها محاسبه می‌شود.

        Returns:
            نرخ برنده بین ۰.۰ تا ۱.۰
        """
        trades = self.get_by_symbol(symbol) if symbol else self._memory
        if not trades:
            return 0.0
        wins = sum(1 for t in trades if t.outcome == TradeOutcome.WIN)
        return wins / len(trades)

    def get_average_rr(self, symbol: Optional[str] = None) -> float:
        """محاسبه میانگین R:R واقعی محقق‌شده"""
        trades = self.get_by_symbol(symbol) if symbol else self._memory
        if not trades:
            return 0.0
        return sum(t.realized_rr for t in trades) / len(trades)

    def get_consecutive_losses(self) -> int:
        """تعداد زیان‌های متوالی اخیر"""
        count = 0
        for trade in reversed(self._memory):
            if trade.outcome == TradeOutcome.LOSS:
                count += 1
            else:
                break
        return count

    def to_feature_matrix(self) -> tuple[List[Dict[str, float]], List[int]]:
        """
        تبدیل حافظه به feature matrix برای ML.

        Returns:
            (features, labels) — label: 1 برای WIN، 0 برای LOSS
        """
        features = []
        labels = []
        for trade in self._memory:
            if trade.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS):
                features.append(trade.to_ml_features())
                labels.append(1 if trade.outcome == TradeOutcome.WIN else 0)
        return features, labels

    def get_stats(self) -> Dict[str, Any]:
        """آمار کلی حافظه"""
        total = len(self._memory)
        wins = sum(1 for t in self._memory if t.outcome == TradeOutcome.WIN)
        losses = sum(1 for t in self._memory if t.outcome == TradeOutcome.LOSS)
        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / total if total > 0 else 0.0,
            "avg_rr": self.get_average_rr(),
            "consecutive_losses": self.get_consecutive_losses(),
            "memory_usage": f"{total}/{self._max_memory}",
        }
