"""
موتور Price Action - نسخه Enterprise

این موتور الگوهای کندلی و ساختار قیمت را با تحلیل context-aware تشخیص می‌دهد:
- Pin Bar, Engulfing, Fakey, Inside Bar, Outside Bar
- Doji, Morning Star, Evening Star
- Three Soldiers, Three Crows
- Breakout, Retest, Compression, Expansion

تمام الگوها با context بررسی می‌شوند:
- trend context
- market structure
- liquidity and SMC zones
- volatility
- support/resistance
- session context
- candle quality
- volume/tick-volume

خروجی استاندارد برای Decision Engine با:
- confidence_score
- quality_score
- entry_context
- invalidation_level
- reason_codes

نویسنده: MT5 Trading Team
تاریخ: 2026-06-15
ورژن: 3.0.0
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from enum import Enum
import numpy as np

from ..core.enums import (
    TrendDirection, TradeDirection, TradingSession,
    MarketStructure, BlockType, FVGType
)
from ..core.logger import get_logger

logger = get_logger("price_action_engine")


# =====================================================
# ثابت‌ها و کدها
# =====================================================

class PatternReasonCode(str, Enum):
    """کدهای دلیل برای الگوهای Price Action"""
    # کندلی
    WICK_REJECTION = "wick_rejection"
    BODY_ENGULF = "body_engulf"
    FALSE_BREAK = "false_break"
    INSIDE_STRUCTURE = "inside_structure"
    OUTSIDE_EXPANSION = "outside_expansion"
    INDECISION = "indecision"
    REVERSAL_CANDIDATE = "reversal_candidate"

    # Context
    TREND_ALIGNED = "trend_aligned"
    TREND_OPPOSING = "trend_opposing"
    AT_SUPPORT = "at_support"
    AT_RESISTANCE = "at_resistance"
    IN_BLOCK_ZONE = "in_block_zone"
    IN_FVG_ZONE = "in_fvg_zone"
    AFTER_LIQUIDITY_SWEEP = "after_liquidity_sweep"
    IN_KILLZONE = "in_killzone"

    # ساختار
    LEVEL_BREAK = "level_break"
    LEVEL_RETEST = "level_retest"
    RANGE_COMPRESSION = "range_compression"
    VOLATILITY_EXPANSION = "volatility_expansion"

    # کیفیت
    STRONG_CANDLE = "strong_candle"
    HIGH_VOLUME = "high_volume"
    MULTI_CONFIRMATION = "multi_confirmation"


class PatternStrength(str, Enum):
    """قدرت الگو"""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class PatternType(str, Enum):
    """نوع الگو"""
    # Single candle
    PIN_BAR = "pin_bar"
    DOJI = "doji"
    MARUBOZU = "marubozu"

    # Double candle
    ENGULFING = "engulfing"
    INSIDE_BAR = "inside_bar"
    OUTSIDE_BAR = "outside_bar"
    HARAMI = "harami"
    PIERCING = "piercing"
    DARK_CLOUD = "dark_cloud"

    # Triple candle
    MORNING_STAR = "morning_star"
    EVENING_STAR = "evening_star"
    THREE_SOLDIERS = "three_soldiers"
    THREE_CROWS = "three_crows"

    # Complex
    FAKEY = "fakey"
    BREAKOUT = "breakout"
    RETEST = "retest"
    COMPRESSION = "compression"
    EXPANSION = "expansion"


# =====================================================
# ساختارهای داده استاندارد
# =====================================================

@dataclass
class StandardPASignal:
    """
    ساختار استاندارد خروجی برای همه الگوهای Price Action

    این ساختار توسط Decision Engine مصرف می‌شود.

    Attributes:
        symbol: نماد معاملاتی
        timeframe: تایم‌فریم
        pattern: نوع الگو
        direction: جهت (bullish, bearish, neutral)
        confidence_score: امتیاز اطمینان (0-100)
        quality_score: امتیاز کیفیت (0-100)
        entry_context: اطلاعات ورود
        invalidation_level: سطح بی اعتباری
        reason_codes: لیست کدهای دلیل
        created_at: زمان ایجاد
        metadata: اطلاعات اضافی
    """
    symbol: str
    timeframe: str
    pattern: PatternType
    direction: str
    confidence_score: float
    quality_score: float
    entry_context: Dict[str, Any]
    invalidation_level: float
    reason_codes: List[PatternReasonCode]
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "pattern": self.pattern.value,
            "direction": self.direction,
            "confidence_score": self.confidence_score,
            "quality_score": self.quality_score,
            "entry_context": self.entry_context,
            "invalidation_level": self.invalidation_level,
            "reason_codes": [rc.value for rc in self.reason_codes],
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class CandleData:
    """داده کندل با اطلاعات کامل"""
    index: int
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    body: float = 0.0
    upper_wick: float = 0.0
    lower_wick: float = 0.0
    total_range: float = 0.0
    body_ratio: float = 0.0
    is_bullish: bool = True

    def __post_init__(self):
        """محاسبه ویژگی‌های کندل"""
        self.body = abs(self.close - self.open)
        self.total_range = self.high - self.low
        self.upper_wick = self.high - max(self.open, self.close)
        self.lower_wick = min(self.open, self.close) - self.low
        self.is_bullish = self.close >= self.open
        self.body_ratio = self.body / self.total_range if self.total_range > 0 else 0


@dataclass
class MarketContext:
    """
    Context بازار برای تحلیل الگوها

    شامل تمام اطلاعات محیطی که بر اعتبار الگو تأثیر می‌گذارد.
    """
    # روند
    trend: TrendDirection = TrendDirection.NEUTRAL
    trend_strength: float = 0.0
    higher_timeframe_trend: TrendDirection = TrendDirection.NEUTRAL

    # ساختار بازار
    last_structure_event: Optional[str] = None
    structure_direction: Optional[TrendDirection] = None

    # نقدینگی
    liquidity_swept: bool = False
    sweep_direction: Optional[str] = None
    sweep_level: Optional[float] = None

    # SMC zones
    active_blocks: List[Dict[str, Any]] = field(default_factory=list)
    active_fvgs: List[Dict[str, Any]] = field(default_factory=list)

    # سطوح
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)

    # Volatility
    atr: float = 0.0
    volatility_percentile: float = 50.0
    avg_range: float = 0.0

    # Session
    current_session: TradingSession = TradingSession.LONDON
    is_killzone: bool = False
    killzone_name: Optional[str] = None

    # Premium/Discount
    premium_discount: str = "equilibrium"
    equilibrium_zone: Tuple[float, float] = (0, 0)

    # قیمت فعلی
    current_price: float = 0.0


@dataclass
class PatternAnalysis:
    """
    نتیجه تحلیل یک الگو با تمام جزئیات
    """
    pattern: PatternType
    detected: bool = False
    direction: str = "neutral"
    candle_indices: List[int] = field(default_factory=list)
    candle_times: List[datetime] = field(default_factory=list)
    base_score: float = 0.0
    confidence_score: float = 0.0
    quality_score: float = 0.0
    invalidation_level: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reason_codes: List[PatternReasonCode] = field(default_factory=list)
    context_bonuses: Dict[str, float] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


# =====================================================
# تحلیلگر Context
# =====================================================

class ContextAnalyzer:
    """
    تحلیلگر Context بازار

    این کلاس تمام اطلاعات محیطی را جمع‌آوری و تحلیل می‌کند
    تا الگوهای Price Action با توجه به context ارزیابی شوند.
    """

    def __init__(self, config: Optional[Dict] = None):
        """مقداردهی اولیه"""
        self.config = config or {}

        # تنظیمات
        self.atr_period = config.get("atr_period", 14)
        self.range_period = config.get("range_period", 20)
        self.volatility_threshold_high = config.get("volatility_threshold_high", 0.8)
        self.volatility_threshold_low = config.get("volatility_threshold_low", 0.3)

        logger.debug("ContextAnalyzer مقداردهی شد")

    def analyze(
        self,
        candles: List[Dict[str, Any]],
        times: List[datetime],
        smc_context: Optional[Dict[str, Any]] = None
    ) -> MarketContext:
        """
        تحلیل کامل context بازار

        Args:
            candles: لیست کندل‌ها
            times: زمان کندل‌ها
            smc_context: context از SMC Engine

        Returns:
            MarketContext: اطلاعات کامل محیطی
        """
        context = MarketContext()

        if not candles or len(candles) < 20:
            logger.warning("داده کافی برای تحلیل context نیست")
            return context

        # محاسبه ATR و volatility
        self._calculate_volatility(candles, context)

        # تشخیص روند
        self._detect_trend(candles, context)

        # تنظیم session
        self._determine_session(times[-1] if times else datetime.utcnow(), context)

        # استخراج SMC context
        if smc_context:
            self._extract_smc_context(smc_context, context)

        # استخراج سطوح
        self._extract_levels(candles, context)

        logger.debug(
            f"Context: روند={context.trend.value} | "
            f"Volatility={context.volatility_percentile:.0f}% | "
            f"Session={context.current_session.value}"
        )

        return context

    def _calculate_volatility(
        self,
        candles: List[Dict[str, Any]],
        context: MarketContext
    ) -> None:
        """محاسبه volatility و ATR"""
        n = len(candles)
        period = min(self.atr_period, n - 1)

        if period < 1:
            return

        # محاسبه True Range برای هر کندل
        true_ranges = []
        for i in range(max(1, n - period), n):
            high = candles[i]['high']
            low = candles[i]['low']
            prev_close = candles[i - 1]['close']

            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)

        if true_ranges:
            context.atr = np.mean(true_ranges)
            context.avg_range = context.atr

        # محاسبه percentile volatility
        if len(true_ranges) >= 10:
            all_ranges = []
            for i in range(max(1, n - self.range_period), n):
                high = candles[i]['high']
                low = candles[i]['low']
                prev_close = candles[i - 1]['close']
                tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                all_ranges.append(tr)

            if all_ranges and context.atr > 0:
                context.volatility_percentile = min(
                    100,
                    max(0, np.percentile(all_ranges, 80) / context.atr * 50)
                )

    def _detect_trend(
        self,
        candles: List[Dict[str, Any]],
        context: MarketContext
    ) -> None:
        """تشخیص روند با چند دوره"""
        n = len(candles)
        lookbacks = [20, 50]

        bullish_votes = 0
        bearish_votes = 0

        for lookback in lookbacks:
            if n < lookback:
                continue

            recent = candles[-lookback:]

            # بررسیEMA
            closes = [c['close'] for c in recent]
            ema_fast = np.mean(closes[-10:])
            ema_slow = np.mean(closes)

            if ema_fast > ema_slow * 1.001:
                bullish_votes += 1
            elif ema_fast < ema_slow * 0.999:
                bearish_votes += 1

            # بررسی swing highs/lows
            highs = [c['high'] for c in recent]
            lows = [c['low'] for c in recent]

            # ساختار HH/HL یا LH/LL
            mid = len(recent) // 2
            first_half_high = max(highs[:mid])
            second_half_high = max(highs[mid:])
            first_half_low = min(lows[:mid])
            second_half_low = min(lows[mid:])

            if second_half_high > first_half_high and second_half_low > first_half_low:
                bullish_votes += 1
            elif second_half_high < first_half_high and second_half_low < first_half_low:
                bearish_votes += 1

        # تعیین روند
        if bullish_votes >= 2:
            context.trend = TrendDirection.BULLISH
            context.trend_strength = min(bullish_votes / max(bullish_votes + bearish_votes, 1) * 100, 100)
        elif bearish_votes >= 2:
            context.trend = TrendDirection.BEARISH
            context.trend_strength = min(bearish_votes / max(bullish_votes + bearish_votes, 1) * 100, 100)
        else:
            context.trend = TrendDirection.NEUTRAL
            context.trend_strength = 30

    def _determine_session(
        self,
        current_time: datetime,
        context: MarketContext
    ) -> None:
        """تعیین سشن معاملاتی"""
        hour = current_time.hour

        # تعریف سشن‌ها (UTC)
        sessions = {
            TradingSession.SYDNEY: (22, 7),
            TradingSession.TOKYO: (0, 9),
            TradingSession.LONDON: (8, 17),
            TradingSession.NEW_YORK: (13, 22)
        }

        # Kill zones
        killzones = {
            "london": (8.0, 11.0),
            "new_york": (13.5, 16.0),
            "tokyo": (0.5, 2.0)
        }

        current_decimal_hour = hour + current_time.minute / 60

        # تعیین سشن فعال
        for session, (open_h, close_h) in sessions.items():
            if open_h > close_h:
                is_active = current_decimal_hour >= open_h or current_decimal_hour < close_h
            else:
                is_active = open_h <= current_decimal_hour < close_h

            if is_active:
                context.current_session = session
                break

        # تعیین kill zone
        for kz_name, (kz_start, kz_end) in killzones.items():
            if kz_start <= current_decimal_hour < kz_end:
                context.is_killzone = True
                context.killzone_name = kz_name
                break

    def _extract_smc_context(
        self,
        smc_context: Dict[str, Any],
        context: MarketContext
    ) -> None:
        """استخراج اطلاعات از SMC Engine"""
        context.last_structure_event = smc_context.get("last_event_type")
        context.liquidity_swept = smc_context.get("liquidity_swept", False)
        context.sweep_direction = smc_context.get("sweep_direction")

        # Active blocks
        for block in smc_context.get("active_blocks", []):
            block_data = {
                "type": block.get("block_type", "order_block"),
                "direction": block.get("direction", "bullish"),
                "high": block.get("high", 0),
                "low": block.get("low", 0),
                "mid": block.get("mid", 0),
                "strength": block.get("score", 5)
            }
            context.active_blocks.append(block_data)

            # اضافه به سطوح
            if block.get("direction") == "bullish":
                context.support_levels.append(block.get("low", 0))
            else:
                context.resistance_levels.append(block.get("high", 0))

        # Active FVGs
        for fvg in smc_context.get("active_fvgs", []):
            fvg_data = {
                "type": fvg.get("fvg_type", "bullish_fvg"),
                "high": fvg.get("high", 0),
                "low": fvg.get("low", 0),
                "mid": fvg.get("mid", 0)
            }
            context.active_fvgs.append(fvg_data)

        # Premium/Discount
        context.premium_discount = smc_context.get("premium_discount", "equilibrium")
        if "equilibrium_zone" in smc_context:
            eq = smc_context["equilibrium_zone"]
            if isinstance(eq, (list, tuple)) and len(eq) == 2:
                context.equilibrium_zone = (eq[0], eq[1])

    def _extract_levels(
        self,
        candles: List[Dict[str, Any]],
        context: MarketContext
    ) -> None:
        """استخراج سطوح کلیدی"""
        n = len(candles)
        lookback = min(50, n)

        recent = candles[-lookback:]

        # سقف‌های اخیر
        for i in range(2, len(recent) - 2):
            if (recent[i]['high'] > recent[i-1]['high'] and
                recent[i]['high'] > recent[i-2]['high'] and
                recent[i]['high'] > recent[i+1]['high'] and
                recent[i]['high'] > recent[i+2]['high']):
                context.resistance_levels.append(recent[i]['high'])

        # کف‌های اخیر
        for i in range(2, len(recent) - 2):
            if (recent[i]['low'] < recent[i-1]['low'] and
                recent[i]['low'] < recent[i-2]['low'] and
                recent[i]['low'] < recent[i+1]['low'] and
                recent[i]['low'] < recent[i+2]['low']):
                context.support_levels.append(recent[i]['low'])

        # حذف تکراری‌ها و مرتب‌سازی
        context.resistance_levels = sorted(set(context.resistance_levels), reverse=True)[:10]
        context.support_levels = sorted(set(context.support_levels), reverse=True)[:10]


# =====================================================
# تشخیص الگوهای کندلی
# =====================================================

class CandlePatternDetector:
    """
    تشخیص الگوهای کندلی با context-aware

    هر الگو نه تنها از روی شکل کندل تشخیص داده می‌شود
    بلکه با توجه به context بازار ارزیابی می‌شود.
    """

    def __init__(self, config: Optional[Dict] = None):
        """مقداردهی اولیه"""
        self.config = config or {}

        # آستانه‌ها
        self.pin_wick_min_ratio = config.get("pin_wick_min_ratio", 0.6)
        self.pin_body_max_ratio = config.get("pin_body_max_ratio", 0.35)
        self.engulf_min_ratio = config.get("engulf_min_ratio", 1.2)
        self.doji_max_body_ratio = config.get("doji_max_body_ratio", 0.1)

        logger.debug("CandlePatternDetector مقداردهی شد")

    def detect_pin_bar(
        self,
        candles: List[CandleData],
        context: MarketContext,
        index: int = -1
    ) -> PatternAnalysis:
        """
        تشخیص الگوی Pin Bar با context

        Pin Bar کندلی است با:
        - بدنه کوچک (کمتر از 35% رنج)
        - سایه بلند یک طرف (بیشتر از 60%)
        - سایه کوچک طرف دیگر (کمتر از 15%)

        Context bonuses:
        - در جهت روند: +20%
        - در حمایت/مقاومت: +15%
        - در OB/FVG: +15%
        - پس از liquidity sweep: +20%
        - در kill zone: +10%

        Returns:
            PatternAnalysis: نتیجه تحلیل
        """
        analysis = PatternAnalysis(pattern=PatternType.PIN_BAR)

        if not candles:
            return analysis

        candle = candles[index]
        if candle.total_range == 0:
            return analysis

        upper_wick_pct = candle.upper_wick / candle.total_range
        lower_wick_pct = candle.lower_wick / candle.total_range
        body_pct = candle.body_ratio

        # Bullish Pin Bar (lower wick)
        if (lower_wick_pct >= self.pin_wick_min_ratio and
            body_pct <= self.pin_body_max_ratio and
            upper_wick_pct <= 0.15):

            analysis.detected = True
            analysis.direction = "bullish"
            analysis.base_score = 8.0
            analysis.details = {
                "wick_level": candle.low,
                "wick_ratio": lower_wick_pct,
                "body_ratio": body_pct
            }
            analysis.reason_codes.append(PatternReasonCode.WICK_REJECTION)

        # Bearish Pin Bar (upper wick)
        elif (upper_wick_pct >= self.pin_wick_min_ratio and
              body_pct <= self.pin_body_max_ratio and
              lower_wick_pct <= 0.15):

            analysis.detected = True
            analysis.direction = "bearish"
            analysis.base_score = 8.0
            analysis.details = {
                "wick_level": candle.high,
                "wick_ratio": upper_wick_pct,
                "body_ratio": body_pct
            }
            analysis.reason_codes.append(PatternReasonCode.WICK_REJECTION)

        if not analysis.detected:
            return analysis

        # Context analysis
        self._apply_context_bonuses(analysis, context, candle)

        # محاسبه scores نهایی
        self._calculate_final_scores(analysis, context)

        # تنظیم invalidation level
        if analysis.direction == "bullish":
            analysis.invalidation_level = candle.low - context.atr * 0.5
        else:
            analysis.invalidation_level = candle.high + context.atr * 0.5

        analysis.candle_indices = [candle.index]
        analysis.candle_times = [candle.time]

        logger.info(
            f"Pin Bar {analysis.direction} | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_engulfing(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص الگوی Engulfing با context

        Engulfing شامل دو کندل است:
        - کندل اول: بدنه کوچک در یک جهت
        - کندل دوم: بدنه بزرگ که اولی را engulf می‌کند

        Conditions:
        - Body دوم باید حداقل 120% اول باشد
        - جهت کندل‌ها مخالف باشد
        """
        analysis = PatternAnalysis(pattern=PatternType.ENGULFING)

        if len(candles) < 2:
            return analysis

        prev = candles[-2]
        curr = candles[-1]

        # بررسی engulfing
        prev_body_start = min(prev.open, prev.close)
        prev_body_end = max(prev.open, prev.close)
        curr_body_start = min(curr.open, curr.close)
        curr_body_end = max(curr.open, curr.close)

        # Bullish Engulfing
        if (curr.is_bullish and not prev.is_bullish and
            curr_body_start <= prev_body_start and
            curr_body_end >= prev_body_end and
            curr.body >= prev.body * self.engulf_min_ratio):

            analysis.detected = True
            analysis.direction = "bullish"
            analysis.base_score = 10.0
            analysis.details = {
                "engulf_ratio": curr.body / max(prev.body, 0.0001),
                "prev_body": prev.body,
                "curr_body": curr.body
            }
            analysis.reason_codes.append(PatternReasonCode.BODY_ENGULF)

        # Bearish Engulfing
        elif (not curr.is_bullish and prev.is_bullish and
              curr_body_start <= prev_body_start and
              curr_body_end >= prev_body_end and
              curr.body >= prev.body * self.engulf_min_ratio):

            analysis.detected = True
            analysis.direction = "bearish"
            analysis.base_score = 10.0
            analysis.details = {
                "engulf_ratio": curr.body / max(prev.body, 0.0001),
                "prev_body": prev.body,
                "curr_body": curr.body
            }
            analysis.reason_codes.append(PatternReasonCode.BODY_ENGULF)

        if not analysis.detected:
            return analysis

        # Context analysis
        self._apply_context_bonuses(analysis, context, curr)

        # بررسی قدرت کندل engulfing
        if curr.body_ratio >= 0.7:
            analysis.context_bonuses["strong_body"] = 10
            analysis.reason_codes.append(PatternReasonCode.STRONG_CANDLE)

        # محاسبه scores نهایی
        self._calculate_final_scores(analysis, context)

        # تنظیم levels
        if analysis.direction == "bullish":
            analysis.invalidation_level = curr.low - context.atr * 0.5
            analysis.entry_price = curr.close
        else:
            analysis.invalidation_level = curr.high + context.atr * 0.5
            analysis.entry_price = curr.close

        analysis.candle_indices = [prev.index, curr.index]
        analysis.candle_times = [prev.time, curr.time]

        logger.info(
            f"Engulfing {analysis.direction} | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_fakey(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص الگوی Fakey با context

        Fakey الگوی فریب بازار:
        1. Mother Bar (کندل بزرگ)
        2. Inside Bar (کندل داخل mother)
        3. False Break (شکست جعلی مناطق inside bar)
        4. Return و بسته شدن داخل mother

        این الگو یکی از قدرتمندترین الگوهای reversal است.
        """
        analysis = PatternAnalysis(
            pattern=PatternType.FAKEY,
            base_score=15.0
        )

        if len(candles) < 4:
            return analysis

        mother = candles[-4]
        inside = candles[-3]
        test_candle = candles[-2]
        signal_candle = candles[-1]

        # بررسی Inside Bar
        is_inside = (inside.high <= mother.high and
                    inside.low >= mother.low)

        if not is_inside:
            return analysis

        # بررسی Mother Bar باید بزرگ باشد
        if mother.body_ratio < 0.4 or mother.total_range < context.avg_range * 0.8:
            return analysis

        # Bearish Fakey (false break up)
        if (test_candle.high > inside.high and
            signal_candle.close < inside.high and
            signal_candle.close < mother.high):

            analysis.detected = True
            analysis.direction = "bearish"
            analysis.details = {
                "mother_range": mother.total_range,
                "false_break_level": inside.high,
                "test_high": test_candle.high
            }
            analysis.reason_codes.append(PatternReasonCode.FALSE_BREAK)

        # Bullish Fakey (false break down)
        elif (test_candle.low < inside.low and
              signal_candle.close > inside.low and
              signal_candle.close > mother.low):

            analysis.detected = True
            analysis.direction = "bullish"
            analysis.details = {
                "mother_range": mother.total_range,
                "false_break_level": inside.low,
                "test_low": test_candle.low
            }
            analysis.reason_codes.append(PatternReasonCode.FALSE_BREAK)

        if not analysis.detected:
            return analysis

        # Context bonuses
        self._apply_context_bonuses(analysis, context, signal_candle)

        # Fakey در جهت مخالف روند قوی‌تر است (reversal)
        if context.trend != TrendDirection.NEUTRAL:
            if (context.trend == TrendDirection.BULLISH and analysis.direction == "bearish") or \
               (context.trend == TrendDirection.BEARISH and analysis.direction == "bullish"):
                analysis.context_bonuses["counter_trend_reversal"] = 15
                analysis.reason_codes.append(PatternReasonCode.REVERSAL_CANDIDATE)

        self._calculate_final_scores(analysis, context)

        # Levels
        if analysis.direction == "bullish":
            analysis.invalidation_level = mother.low - context.atr * 0.3
            analysis.entry_price = signal_candle.close
            analysis.stop_loss = mother.low
        else:
            analysis.invalidation_level = mother.high + context.atr * 0.3
            analysis.entry_price = signal_candle.close
            analysis.stop_loss = mother.high

        analysis.candle_indices = [mother.index, inside.index, test_candle.index, signal_candle.index]
        analysis.candle_times = [mother.time, inside.time, test_candle.time, signal_candle.time]

        logger.info(
            f"Fakey {analysis.direction} | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_inside_bar(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص Inside Bar با context

        Inside Bar کندلی است که کاملاً داخل
        محدوده کندل قبلی (Mother Bar) قرار دارد.

        نشان‌دهنده فشردگی و آماده‌شدن برای حرکت بزرگ.
        """
        analysis = PatternAnalysis(pattern=PatternType.INSIDE_BAR)

        if len(candles) < 2:
            return analysis

        mother = candles[-2]
        inside = candles[-1]

        # بررسی inside
        if inside.high <= mother.high and inside.low >= mother.low:
            analysis.detected = True
            analysis.direction = "neutral"  # until break
            analysis.base_score = 5.0
            analysis.details = {
                "mother_high": mother.high,
                "mother_low": mother.low,
                "mother_range": mother.total_range,
                "inside_range": inside.total_range
            }
            analysis.reason_codes.append(PatternReasonCode.INSIDE_STRUCTURE)

        if not analysis.detected:
            return analysis

        # Context bonuses
        self._apply_context_bonuses(analysis, context, inside)

        # اگر mother bar large باشد
        if mother.total_range > context.avg_range * 1.2:
            analysis.context_bonuses["large_mother"] = 10

        # اگر inside bar خیلی کوچک باشد (compression)
        if inside.total_range < mother.total_range * 0.3:
            analysis.context_bonuses["strong_compression"] = 10
            analysis.reason_codes.append(PatternReasonCode.IN_SIDE_STRUCTURE)

        self._calculate_final_scores(analysis, context)

        # برای Inside Bar، invalidation در هر دو طرف
        analysis.invalidation_level = (mother.high + mother.low) / 2
        analysis.details["breakout_level_high"] = mother.high
        analysis.details["breakout_level_low"] = mother.low

        analysis.candle_indices = [mother.index, inside.index]
        analysis.candle_times = [mother.time, inside.time]

        logger.info(
            f"Inside Bar | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_outside_bar(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص Outside Bar با context

        Outside Bar کندلی است که محدوده
        کندل قبلی را کامل پوشش می‌دهد.

        نشان‌دهنده تغییر کنترل بازار است.
        """
        analysis = PatternAnalysis(pattern=PatternType.OUTSIDE_BAR)

        if len(candles) < 2:
            return analysis

        prev = candles[-2]
        curr = candles[-1]

        # بررسی خارج شدن از محدوده قبلی
        is_outside = (curr.high > prev.high and curr.low < prev.low)

        if not is_outside:
            return analysis

        # بررسی قدرت کندل
        if curr.body_ratio >= 0.5:
            analysis.detected = True
            analysis.direction = "bullish" if curr.is_bullish else "bearish"
            analysis.base_score = 9.0
            analysis.reason_codes.append(PatternReasonCode.OUTSIDE_EXPANSION)

            analysis.details = {
                "prev_high": prev.high,
                "prev_low": prev.low,
                "curr_high": curr.high,
                "curr_low": curr.low,
                "expansion_up": curr.high - prev.high,
                "expansion_down": prev.low - curr.low
            }

        if not analysis.detected:
            return analysis

        # Context bonuses
        self._apply_context_bonuses(analysis, context, curr)

        # قوی‌تر در جهت روند
        if context.trend != TrendDirection.NEUTRAL:
            if (context.trend == TrendDirection.BULLISH and analysis.direction == "bullish") or \
               (context.trend == TrendDirection.BEARISH and analysis.direction == "bearish"):
                analysis.context_bonuses["trend_aligned"] = 15
                analysis.reason_codes.append(PatternReasonCode.TREND_ALIGNED)

        self._calculate_final_scores(analysis, context)

        # Levels
        if analysis.direction == "bullish":
            analysis.invalidation_level = curr.low - context.atr * 0.5
        else:
            analysis.invalidation_level = curr.high + context.atr * 0.5

        analysis.candle_indices = [prev.index, curr.index]
        analysis.candle_times = [prev.time, curr.time]

        logger.info(
            f"Outside Bar {analysis.direction} | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_doji(
        self,
        candles: List[CandleData],
        context: MarketContext,
        index: int = -1
    ) -> PatternAnalysis:
        """
        تشخیص Doji با context

        Doji نشان‌دهنده عدم تصمیم بازار است.
        - بدنه خیلی کوچک (کمتر از 10% رنج)
        - قیمت باز و بسته تقریباً برابر
        """
        analysis = PatternAnalysis(pattern=PatternType.DOJI)

        if not candles:
            return analysis

        candle = candles[index]

        # بررسی doji
        if candle.body_ratio <= self.doji_max_body_ratio and candle.total_range > 0:
            analysis.detected = True
            analysis.direction = "neutral"
            analysis.base_score = 4.0
            analysis.reason_codes.append(PatternReasonCode.INDECISION)

            analysis.details = {
                "mid_level": (candle.high + candle.low) / 2,
                "body_ratio": candle.body_ratio,
                "range": candle.total_range
            }

        if not analysis.detected:
            return analysis

        # Context bonuses برای Doji
        # Doji در support/resistance مهم‌تر است
        current_level = (candle.high + candle.low) / 2

        for support in context.support_levels[:3]:
            if abs(current_level - support) < context.atr * 0.5:
                analysis.context_bonuses["at_support"] = 10
                analysis.reason_codes.append(PatternReasonCode.AT_SUPPORT)
                break

        for resistance in context.resistance_levels[:3]:
            if abs(current_level - resistance) < context.atr * 0.5:
                analysis.context_bonuses["at_resistance"] = 10
                analysis.reason_codes.append(PatternReasonCode.AT_RESISTANCE)
                break

        # Doji بعد از روند قوی = potential reversal
        if context.trend_strength > 60:
            analysis.context_bonuses["potential_reversal"] = 10
            analysis.reason_codes.append(PatternReasonCode.REVERSAL_CANDIDATE)

        self._calculate_final_scores(analysis, context)

        analysis.candle_indices = [candle.index]
        analysis.candle_times = [candle.time]

        logger.info(
            f"Doji | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_star_pattern(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص Morning Star و Evening Star با context

        ساختار سه کندلی:
        - کندل اول: در جهت روند قبلی (بدنه بزرگ)
        - کندل وسط: بدنه کوچک (star)
        - کندل سوم: در جهت مخالف (بدنه بزرگ)

        Morning Star: نزولی -> کوچک -> صعودی
        Evening Star: صعودی -> کوچک -> نزولی
        """
        analysis = PatternAnalysis(pattern=PatternType.MORNING_STAR)

        if len(candles) < 3:
            return analysis

        first = candles[-3]
        middle = candles[-2]
        last = candles[-1]

        first_body = first.body
        middle_body = middle.body
        last_body = last.body

        # Morning Star (bullish reversal)
        if (not first.is_bullish and  # نزولی
            middle_body < first_body * 0.4 and  # کوچک
            last.is_bullish and  # صعودی
            last_body > middle_body * 2 and  # بزرگ
            last.close > (first.open + first.close) / 2):  # بالاتر از mid first

            analysis.detected = True
            analysis.pattern = PatternType.MORNING_STAR
            analysis.direction = "bullish"
            analysis.base_score = 12.0
            analysis.reason_codes.append(PatternReasonCode.REVERSAL_CANDIDATE)

            analysis.details = {
                "first_body": first_body,
                "middle_body": middle_body,
                "last_body": last_body,
                "reversal_strength": last_body / max(middle_body, 0.0001)
            }

        # Evening Star (bearish reversal)
        elif (first.is_bullish and  # صعودی
              middle_body < first_body * 0.4 and  # کوچک
              not last.is_bullish and  # نزولی
              last_body > middle_body * 2 and  # بزرگ
              last.close < (first.open + first.close) / 2):  # پایین‌تر از mid first

            analysis.detected = True
            analysis.pattern = PatternType.EVENING_STAR
            analysis.direction = "bearish"
            analysis.base_score = 12.0
            analysis.reason_codes.append(PatternReasonCode.REVERSAL_CANDIDATE)

            analysis.details = {
                "first_body": first_body,
                "middle_body": middle_body,
                "last_body": last_body,
                "reversal_strength": last_body / max(middle_body, 0.0001)
            }

        if not analysis.detected:
            return analysis

        # Context bonuses
        self._apply_context_bonuses(analysis, context, last)

        # Star pattern قوی‌تر در top/bottom
        if analysis.direction == "bullish" and context.premium_discount == "discount":
            analysis.context_bonuses["in_discount_zone"] = 10
        elif analysis.direction == "bearish" and context.premium_discount == "premium":
            analysis.context_bonuses["in_premium_zone"] = 10

        self._calculate_final_scores(analysis, context)

        # Levels
        if analysis.direction == "bullish":
            analysis.invalidation_level = min(first.low, middle.low, last.low) - context.atr * 0.3
        else:
            analysis.invalidation_level = max(first.high, middle.high, last.high) + context.atr * 0.3

        analysis.candle_indices = [first.index, middle.index, last.index]
        analysis.candle_times = [first.time, middle.time, last.time]

        pattern_name = analysis.pattern.value
        logger.info(
            f"{pattern_name} {analysis.direction} | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def detect_three_soldiers_crows(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص Three White Soldiers و Three Black Crows با context

        سه کندل متوالی در یک جهت با:
        - بدنه‌های بزرگ
        - افزایش/کاهش تدریجی قیمت
        - سایه‌های کوچک در هر کندل
        """
        analysis = PatternAnalysis(pattern=PatternType.THREE_SOLDIERS)

        if len(candles) < 3:
            return analysis

        c1 = candles[-3]
        c2 = candles[-2]
        c3 = candles[-1]

        # Three White Soldiers
        if (c1.is_bullish and c2.is_bullish and c3.is_bullish and
            c2.close > c1.close and c3.close > c2.close):

            # بررسی سایه‌های کوچک
            small_wicks = (
                c1.upper_wick < c1.body * 0.5 and
                c2.upper_wick < c2.body * 0.5 and
                c3.upper_wick < c3.body * 0.5
            )

            if small_wicks:
                analysis.detected = True
                analysis.pattern = PatternType.THREE_SOLDIERS
                analysis.direction = "bullish"
                analysis.base_score = 11.0
                analysis.reason_codes.append(PatternReasonCode.TREND_ALIGNED)

                total_move = c3.close - c1.open
                analysis.details = {
                    "total_move": total_move,
                    "avg_body": (c1.body + c2.body + c3.body) / 3,
                    "small_wicks": True
                }

        # Three Black Crows
        elif (not c1.is_bullish and not c2.is_bullish and not c3.is_bullish and
              c2.close < c1.close and c3.close < c2.close):

            small_wicks = (
                c1.lower_wick < c1.body * 0.5 and
                c2.lower_wick < c2.body * 0.5 and
                c3.lower_wick < c3.body * 0.5
            )

            if small_wicks:
                analysis.detected = True
                analysis.pattern = PatternType.THREE_CROWS
                analysis.direction = "bearish"
                analysis.base_score = 11.0
                analysis.reason_codes.append(PatternReasonCode.TREND_ALIGNED)

                total_move = c1.open - c3.close
                analysis.details = {
                    "total_move": total_move,
                    "avg_body": (c1.body + c2.body + c3.body) / 3,
                    "small_wicks": True
                }

        if not analysis.detected:
            return analysis

        # Context bonuses
        self._apply_context_bonuses(analysis, context, c3)

        # قوی‌تر اگر با روند هماهنگ باشد
        if ((context.trend == TrendDirection.BULLISH and analysis.direction == "bullish") or
            (context.trend == TrendDirection.BEARISH and analysis.direction == "bearish")):
            analysis.context_bonuses["trend_continuation"] = 15

        self._calculate_final_scores(analysis, context)

        # Levels
        if analysis.direction == "bullish":
            analysis.invalidation_level = c1.open - context.atr * 0.5
        else:
            analysis.invalidation_level = c1.open + context.atr * 0.5

        analysis.candle_indices = [c1.index, c2.index, c3.index]
        analysis.candle_times = [c1.time, c2.time, c3.time]

        pattern_name = analysis.pattern.value
        logger.info(
            f"{pattern_name} {analysis.direction} | اعتماد: {analysis.confidence_score:.0f}% | "
            f"کیفیت: {analysis.quality_score:.0f}%"
        )

        return analysis

    def _apply_context_bonuses(
        self,
        analysis: PatternAnalysis,
        context: MarketContext,
        signal_candle: CandleData
    ) -> None:
        """
        اعمال bonuses بر اساس context بازار
        """
        candle_mid = (signal_candle.high + signal_candle.low) / 2

        # با روند
        if context.trend != TrendDirection.NEUTRAL:
            if ((context.trend == TrendDirection.BULLISH and analysis.direction == "bullish") or
                (context.trend == TrendDirection.BEARISH and analysis.direction == "bearish")):
                analysis.context_bonuses["trend_aligned"] = 15
                analysis.reason_codes.append(PatternReasonCode.TREND_ALIGNED)
            elif ((context.trend == TrendDirection.BULLISH and analysis.direction == "bearish") or
                  (context.trend == TrendDirection.BEARISH and analysis.direction == "bullish")):
                analysis.context_bonuses["counter_trend"] = 5
                analysis.reason_codes.append(PatternReasonCode.TREND_OPPOSING)

        # در حمایت/مقاومت
        for support in context.support_levels[:3]:
            if abs(candle_mid - support) < context.atr * 0.5:
                if analysis.direction == "bullish":
                    analysis.context_bonuses["at_support"] = 15
                    analysis.reason_codes.append(PatternReasonCode.AT_SUPPORT)
                break

        for resistance in context.resistance_levels[:3]:
            if abs(candle_mid - resistance) < context.atr * 0.5:
                if analysis.direction == "bearish":
                    analysis.context_bonuses["at_resistance"] = 15
                    analysis.reason_codes.append(PatternReasonCode.AT_RESISTANCE)
                break

        # در Order Block
        for block in context.active_blocks:
            if block["low"] <= candle_mid <= block["high"]:
                if ((block["direction"] == "bullish" and analysis.direction == "bullish") or
                    (block["direction"] == "bearish" and analysis.direction == "bearish")):
                    analysis.context_bonuses["in_block_zone"] = 15
                    analysis.reason_codes.append(PatternReasonCode.IN_BLOCK_ZONE)
                break

        # در FVG
        for fvg in context.active_fvgs:
            if fvg["low"] <= candle_mid <= fvg["high"]:
                analysis.context_bonuses["in_fvg_zone"] = 10
                analysis.reason_codes.append(PatternReasonCode.IN_FVG_ZONE)
                break

        # بعد از liquidity sweep
        if context.liquidity_swept:
            if ((context.sweep_direction == "sell_side_hit" and analysis.direction == "bullish") or
                (context.sweep_direction == "buy_side_hit" and analysis.direction == "bearish")):
                analysis.context_bonuses["after_sweep"] = 20
                analysis.reason_codes.append(PatternReasonCode.AFTER_LIQUIDITY_SWEEP)

        # در kill zone
        if context.is_killzone:
            analysis.context_bonuses["killzone"] = 10
            analysis.reason_codes.append(PatternReasonCode.IN_KILLZONE)

        # کندل قوی
        if signal_candle.body_ratio >= 0.7:
            analysis.context_bonuses["strong_candle"] = 10
            analysis.reason_codes.append(PatternReasonCode.STRONG_CANDLE)

        # حجم بالا (اگر موجود باشد)
        if signal_candle.volume > 0:
            analysis.details["volume"] = signal_candle.volume

    def _calculate_final_scores(
        self,
        analysis: PatternAnalysis,
        context: MarketContext
    ) -> None:
        """
        محاسبه امتیازهای نهایی confidence و quality
        """
        # Base confidence از امتیاز الگو
        base_confidence = min(analysis.base_score * 4, 60)

        # Total context bonus
        context_bonus = sum(analysis.context_bonuses.values())

        # Confidence = base + context (max 100)
        analysis.confidence_score = min(base_confidence + context_bonus, 100)

        # Quality score بر اساس تعداد confirmations
        confirmation_count = len(analysis.reason_codes)
        analysis.quality_score = min(40 + confirmation_count * 10 + context_bonus * 0.3, 100)

        # Apply strength adjustment
        if analysis.confidence_score >= 80:
            analysis.details["strength"] = PatternStrength.VERY_STRONG.value
        elif analysis.confidence_score >= 60:
            analysis.details["strength"] = PatternStrength.STRONG.value
        elif analysis.confidence_score >= 40:
            analysis.details["strength"] = PatternStrength.MODERATE.value
        else:
            analysis.details["strength"] = PatternStrength.WEAK.value


# =====================================================
# تحلیلگر ساختار قیمت
# =====================================================

class PriceStructureAnalyzer:
    """
    تحلیلگر ساختار قیمت

    تشخیص:
    - Breakout: شکست سطوح کلیدی
    - Retest: تست مجدد سطح شکسته شده
    - Compression: فشردگی نوسانات
    - Expansion: گسترش نوسانات
    """

    def __init__(self, config: Optional[Dict] = None):
        """مقداردهی اولیه"""
        self.config = config or {}

        self.compression_lookback = config.get("compression_lookback", 10)
        self.compression_ratio_threshold = config.get("compression_ratio_threshold", 0.5)
        self.expansion_ratio_threshold = config.get("expansion_ratio_threshold", 1.5)

        # ردیابی
        self.recent_breakouts: List[Dict[str, Any]] = []
        self.compression_detected_time: Optional[datetime] = None
        self.compression_level: float = 0.0

        logger.debug("PriceStructureAnalyzer مقداردهی شد")

    def analyze(
        self,
        candles: List[CandleData],
        context: MarketContext,
        times: List[datetime]
    ) -> List[PatternAnalysis]:
        """
        تحلیل کامل ساختار قیمت

        Args:
            candles: لیست کندل‌های پردازش شده
            context: context بازار
            times: زمان کندل‌ها

        Returns:
            List[PatternAnalysis]: لیست ساختارهای تشخیص داده شده
        """
        structures = []

        if len(candles) < 20:
            return structures

        # Breakout detection
        breakout = self._detect_breakout(candles, context)
        if breakout.detected:
            structures.append(breakout)

        # Retest detection
        retest = self._detect_retest(candles, context)
        if retest.detected:
            structures.append(retest)

        # Compression detection
        compression = self._detect_compression(candles, context)
        if compression.detected:
            structures.append(compression)
            self.compression_detected_time = times[-1] if times else datetime.utcnow()
            self.compression_level = compression.details.get("mid_level", 0)

        # Expansion detection
        if self.compression_detected_time:
            expansion = self._detect_expansion(candles, context, times)
            if expansion.detected:
                structures.append(expansion)

        return structures

    def _detect_breakout(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """تشخیص شکست سطوح"""
        analysis = PatternAnalysis(pattern=PatternType.BREAKOUT)

        if len(candles) < 2:
            return analysis

        prev = candles[-2]
        curr = candles[-1]

        # بررسی شکست مقاومت
        for resistance in context.resistance_levels[:5]:
            if prev.close < resistance and curr.close > resistance:
                # تأیید با کندل
                if curr.body_ratio >= 0.5 and curr.is_bullish:
                    analysis.detected = True
                    analysis.direction = "bullish"
                    analysis.base_score = 10.0
                    analysis.reason_codes.append(PatternReasonCode.LEVEL_BREAK)

                    analysis.details = {
                        "level": resistance,
                        "break_type": "resistance",
                        "candle_body_ratio": curr.body_ratio
                    }
                    analysis.invalidation_level = resistance - context.atr

                    self.recent_breakouts.append({
                        "level": resistance,
                        "direction": "bullish",
                        "time": curr.time,
                        "candle_index": curr.index
                    })

                    logger.info(f"Breakout صعودی از سطح {resistance:.5f}")
                    break

        # بررسی شکست حمایت
        if not analysis.detected:
            for support in context.support_levels[:5]:
                if prev.close > support and curr.close < support:
                    if curr.body_ratio >= 0.5 and not curr.is_bullish:
                        analysis.detected = True
                        analysis.direction = "bearish"
                        analysis.base_score = 10.0
                        analysis.reason_codes.append(PatternReasonCode.LEVEL_BREAK)

                        analysis.details = {
                            "level": support,
                            "break_type": "support",
                            "candle_body_ratio": curr.body_ratio
                        }
                        analysis.invalidation_level = support + context.atr

                        self.recent_breakouts.append({
                            "level": support,
                            "direction": "bearish",
                            "time": curr.time,
                            "candle_index": curr.index
                        })

                        logger.info(f"Breakout نزولی از سطح {support:.5f}")
                        break

        if analysis.detected:
            # Context bonuses
            if context.is_killzone:
                analysis.context_bonuses["killzone_breakout"] = 15
                analysis.reason_codes.append(PatternReasonCode.IN_KILLZONE)

            # Calculate scores
            base_confidence = min(analysis.base_score * 5, 50)
            context_bonus = sum(analysis.context_bonuses.values())
            analysis.confidence_score = min(base_confidence + context_bonus, 100)
            analysis.quality_score = min(50 + context_bonus, 100)

            analysis.candle_indices = [curr.index]
            analysis.candle_times = [curr.time]

        return analysis

    def _detect_retest(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """تشخیص تست مجدد سطح شکسته شده"""
        analysis = PatternAnalysis(pattern=PatternType.RETEST)

        if len(candles) < 3 or not self.recent_breakouts:
            return analysis

        curr = candles[-1]

        # فقط breakouts اخیر (حداکثر 5 کندل قبل)
        recent_breaks = [b for b in self.recent_breakouts
                       if curr.index - b["candle_index"] <= 5]

        for breakout in recent_breaks:
            level = breakout["level"]
            direction = breakout["direction"]

            # بررسی نزدیک شدن به سطح
            distance_to_level = abs(curr.close - level)

            if distance_to_level < context.atr * 0.3:
                # بررسی rejection از سطح
                if direction == "bullish" and curr.is_bullish:
                    # سطح تبدیل به حمایت شده
                    analysis.detected = True
                    analysis.direction = "bullish"
                    analysis.base_score = 8.0
                    analysis.reason_codes.append(PatternReasonCode.LEVEL_RETEST)

                    analysis.details = {
                        "level": level,
                        "original_breakout_time": breakout["time"],
                        "retest_type": "support_flip"
                    }

                elif direction == "bearish" and not curr.is_bullish:
                    # سطح تبدیل به مقاومت شده
                    analysis.detected = True
                    analysis.direction = "bearish"
                    analysis.base_score = 8.0
                    analysis.reason_codes.append(PatternReasonCode.LEVEL_RETEST)

                    analysis.details = {
                        "level": level,
                        "original_breakout_time": breakout["time"],
                        "retest_type": "resistance_flip"
                    }

                if analysis.detected:
                    analysis.invalidation_level = level

                    logger.info(
                        f"Retest سطح {level:.5f} ({analysis.details.get('retest_type')})"
                    )
                    break

        if analysis.detected:
            # Calculate scores
            analysis.confidence_score = min(analysis.base_score * 5 + 20, 85)
            analysis.quality_score = min(60, 100)

            analysis.candle_indices = [curr.index]
            analysis.candle_times = [curr.time]

        return analysis

    def _detect_compression(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> PatternAnalysis:
        """
        تشخیص فشردگی

        Compression زمانی رخ می‌دهد که نوسانات
        به شدت کاهش می‌یابد - نشانه حرکت بزرگ.
        """
        analysis = PatternAnalysis(pattern=PatternType.COMPRESSION)

        n = len(candles)
        lookback = self.compression_lookback

        if n < lookback * 2:
            return analysis

        # رنج اخیر
        recent = candles[-lookback:]
        recent_ranges = [c.total_range for c in recent]
        recent_avg_range = np.mean(recent_ranges)

        # رنج قبلی
        prev = candles[-lookback * 2:-lookback]
        prev_ranges = [c.total_range for c in prev]
        prev_avg_range = np.mean(prev_ranges)

        if prev_avg_range == 0:
            return analysis

        # نسبت فشردگی
        compression_ratio = recent_avg_range / prev_avg_range

        # بررسی فشردگی قابل توجه
        if compression_ratio < self.compression_ratio_threshold:
            analysis.detected = True
            analysis.direction = "neutral"  # تا مشخص شود
            analysis.base_score = 7.0
            analysis.reason_codes.append(PatternReasonCode.RANGE_COMPRESSION)

            # محدوده فشردگی
            recent_high = max(c.high for c in recent)
            recent_low = min(c.low for c in recent)
            mid_level = (recent_high + recent_low) / 2

            analysis.details = {
                "compression_ratio": compression_ratio,
                "avg_range": recent_avg_range,
                "prev_avg_range": prev_avg_range,
                "high": recent_high,
                "low": recent_low,
                "mid_level": mid_level
            }

            # Context bonuses
            if context.volatility_percentile < 30:
                analysis.context_bonuses["low_volatility"] = 10

            # Calculate scores
            analysis.confidence_score = min(analysis.base_score * 5 + 10, 70)
            analysis.quality_score = min(50 + compression_ratio * 50, 80)

            analysis.candle_indices = [c.index for c in recent[-3:]]
            analysis.candle_times = [c.time for c in recent[-3:]]

            logger.info(
                f"Compression تشخیص داده شد | نسبت: {compression_ratio:.2f}"
            )

        return analysis

    def _detect_expansion(
        self,
        candles: List[CandleData],
        context: MarketContext,
        times: List[datetime]
    ) -> PatternAnalysis:
        """
        تشخیص گسترش نوسانات

        Expansion پس از compression رخ می‌دهد
        و نشان‌دهنده شروع حرکت جدید است.
        """
        analysis = PatternAnalysis(pattern=PatternType.EXPANSION)

        if len(candles) < 3:
            return analysis

        # بررسی زمان компресс (حداکثر 10 کندل بعد)
        curr_time = times[-1] if times else datetime.utcnow()
        if (self.compression_detected_time and
            (curr_time - self.compression_detected_time).total_seconds() > 3600 * 4):
            # خیلی گذشته - reset
            self.compression_detected_time = None
            return analysis

        # کندل‌های اخیر
        recent = candles[-3:]
        recent_avg_range = np.mean([c.total_range for c in recent])

        # مقایسه با avg (قبل از compression)
        if context.avg_range > 0:
            expansion_ratio = recent_avg_range / context.avg_range

            if expansion_ratio >= self.expansion_ratio_threshold:
                # تعیین جهت
                total_move = sum(c.close - c.open for c in recent)

                if total_move > 0:
                    analysis.direction = "bullish"
                else:
                    analysis.direction = "bearish"

                analysis.detected = True
                analysis.base_score = 9.0
                analysis.reason_codes.append(PatternReasonCode.VOLATILITY_EXPANSION)

                analysis.details = {
                    "expansion_ratio": expansion_ratio,
                    "avg_expansion_range": recent_avg_range,
                    "total_move": total_move
                }

                # Context bonuses
                if context.volatility_percentile > 70:
                    analysis.context_bonuses["high_volatility"] = 10

                # Reset compression
                self.compression_detected_time = None

                # Calculate scores
                analysis.confidence_score = min(analysis.base_score * 5 + 15, 80)
                analysis.quality_score = min(60 + expansion_ratio * 10, 90)

                analysis.candle_indices = [c.index for c in recent]
                analysis.candle_times = [c.time for c in recent]

                logger.info(
                    f"Expansion {analysis.direction} | نسبت: {expansion_ratio:.2f}"
                )

        return analysis


# =====================================================
# موتور اصلی Price Action
# =====================================================

class PriceActionEngine:
    """
    موتور اصلی Price Action

    این کلاس تمام الگوهای کندلی و ساختارهای قیمت را
    با تحلیل context-aware تشخیص می‌دهد.

    خروجی استاندارد برای استفاده توسط Decision Engine.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات شامل:
                - atr_period: دوره ATR
                - compression_lookback: دوره compression
                - min_pattern_confidence: حداقل اعتماد برای گزارش
        """
        self.config = config or {}

        # Analyzerها
        self.context_analyzer = ContextAnalyzer(config)
        self.pattern_detector = CandlePatternDetector(config)
        self.structure_analyzer = PriceStructureAnalyzer(config)

        # حداقل اعتماد
        self.min_confidence = config.get("min_pattern_confidence", 30)

        # وزن الگوها برای امتیاز کل
        self.pattern_weights = {
            PatternType.PIN_BAR: 1.0,
            PatternType.ENGULFING: 1.2,
            PatternType.FAKEY: 1.5,
            PatternType.INSIDE_BAR: 0.5,
            PatternType.OUTSIDE_BAR: 0.9,
            PatternType.DOJI: 0.4,
            PatternType.MORNING_STAR: 1.3,
            PatternType.EVENING_STAR: 1.3,
            PatternType.THREE_SOLDIERS: 1.1,
            PatternType.THREE_CROWS: 1.1,
            PatternType.BREAKOUT: 1.2,
            PatternType.RETEST: 1.0,
            PatternType.COMPRESSION: 0.6,
            PatternType.EXPANSION: 1.0
        }

        # Symbol و Timeframe جاری
        self._symbol: str = ""
        self._timeframe: str = "H1"

        logger.info("موتور Price Action نسخه Enterprise مقداردهی شد")

    def analyze(
        self,
        symbol: str,
        data: Dict[str, Any],
        timeframe: str = "H1",
        smc_context: Optional[Dict[str, Any]] = None
    ) -> "PriceActionResult":
        """
        تحلیل کامل Price Action

        Args:
            symbol: نماد معاملاتی
            data: دیکشنری داده‌ها شامل:
                - opens, highs, lows, closes, times, volumes (optional)
            timeframe: تایم‌فریم
            smc_context: context از SMC Engine برای بهبود تحلیل

        Returns:
            PriceActionResult: نتیجه کامل تحلیل
        """
        logger.info(f"{'='*50}")
        logger.info(f"شروع تحلیل Price Action برای {symbol} [{timeframe}]")

        self._symbol = symbol
        self._timeframe = timeframe

        # استخراج داده‌ها
        opens = data.get("opens", [])
        highs = data.get("highs", [])
        lows = data.get("lows", [])
        closes = data.get("closes", [])
        times = data.get("times", [])
        volumes = data.get("volumes", [])

        if not all([opens, highs, lows, closes]):
            logger.warning("داده‌های OHLC کامل نیست")
            return self._get_empty_result()

        if times and isinstance(times[0], str):
            times = [datetime.fromisoformat(t) for t in times]

        min_required = 20
        if len(highs) < min_required:
            logger.warning(f"داده کافی نیست: {len(highs)} کندل")
            return self._get_empty_result()

        # تبدیل به CandleData
        candles = self._convert_to_candle_data(
            opens, highs, lows, closes, times, volumes
        )

        if not times:
            times = [datetime.utcnow() - timedelta(minutes=i*15) for i in range(len(candles))]

        # تحلیل Context
        context = self.context_analyzer.analyze(
            [c.__dict__ for c in candles],
            times,
            smc_context
        )
        context.current_price = closes[-1]

        # تشخیص الگوهای کندلی
        patterns = self._detect_all_patterns(candles, context)

        # تحلیل ساختار قیمت
        structures = self.structure_analyzer.analyze(candles, context, times)

        # محاسبه امتیاز کل
        total_score, direction = self._calculate_total_score(patterns, structures)

        # ایجاد سیگنال‌های استاندارد
        standard_signals = self._create_standard_signals(patterns, structures)

        # استخراج سطوح کلیدی
        key_levels = self._extract_key_levels(candles, patterns, structures)

        logger.info(
            f"تحلیل Price Action کامل شد | جهت: {direction} | "
            f"امتیاز: {total_score:.2f} | الگوها: {len(patterns)} | "
            f"ساختارها: {len(structures)}"
        )
        logger.info(f"{'='*50}")

        return PriceActionResult(
            symbol=symbol,
            timeframe=timeframe,
            total_score=total_score,
            direction=direction,
            context=context,
            patterns=patterns,
            structures=structures,
            standard_signals=standard_signals,
            key_levels=key_levels,
            details={
                "pattern_count": len(patterns),
                "structure_count": len(structures),
                "context_summary": {
                    "trend": context.trend.value,
                    "volatility": context.volatility_percentile,
                    "session": context.current_session.value,
                    "is_killzone": context.is_killzone,
                    "liquidity_swept": context.liquidity_swept
                }
            }
        )

    def _convert_to_candle_data(
        self,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        times: List[datetime],
        volumes: List[float]
    ) -> List[CandleData]:
        """تبدیل داده‌ها به CandleData"""
        candles = []
        n = len(opens)

        for i in range(n):
            candle = CandleData(
                index=i,
                time=times[i] if i < len(times) else datetime.utcnow(),
                open=opens[i],
                high=highs[i],
                low=lows[i],
                close=closes[i],
                volume=volumes[i] if volumes and i < len(volumes) else 0
            )
            candles.append(candle)

        return candles

    def _detect_all_patterns(
        self,
        candles: List[CandleData],
        context: MarketContext
    ) -> List[PatternAnalysis]:
        """تشخیص تمام الگوهای کندلی"""
        patterns = []

        # Pin Bar
        pin = self.pattern_detector.detect_pin_bar(candles, context)
        if pin.detected and pin.confidence_score >= self.min_confidence:
            patterns.append(pin)

        # Engulfing
        engulf = self.pattern_detector.detect_engulfing(candles, context)
        if engulf.detected and engulf.confidence_score >= self.min_confidence:
            patterns.append(engulf)

        # Fakey
        fakey = self.pattern_detector.detect_fakey(candles, context)
        if fakey.detected and fakey.confidence_score >= self.min_confidence:
            patterns.append(fakey)

        # Inside Bar
        inside = self.pattern_detector.detect_inside_bar(candles, context)
        if inside.detected and inside.confidence_score >= self.min_confidence:
            patterns.append(inside)

        # Outside Bar
        outside = self.pattern_detector.detect_outside_bar(candles, context)
        if outside.detected and outside.confidence_score >= self.min_confidence:
            patterns.append(outside)

        # Doji
        doji = self.pattern_detector.detect_doji(candles, context)
        if doji.detected and doji.confidence_score >= self.min_confidence:
            patterns.append(doji)

        # Star patterns
        star = self.pattern_detector.detect_star_pattern(candles, context)
        if star.detected and star.confidence_score >= self.min_confidence:
            patterns.append(star)

        # Three Soldiers/Crows
        three = self.pattern_detector.detect_three_soldiers_crows(candles, context)
        if three.detected and three.confidence_score >= self.min_confidence:
            patterns.append(three)

        return patterns

    def _create_standard_signals(
        self,
        patterns: List[PatternAnalysis],
        structures: List[PatternAnalysis]
    ) -> List[StandardPASignal]:
        """ایجاد سیگنال‌های استاندارد"""
        signals = []

        for pattern in patterns:
            if pattern.direction == "neutral":
                continue

            signal = StandardPASignal(
                symbol=self._symbol,
                timeframe=self._timeframe,
                pattern=pattern.pattern,
                direction=pattern.direction,
                confidence_score=pattern.confidence_score,
                quality_score=pattern.quality_score,
                entry_context={
                    "pattern_type": pattern.pattern.value,
                    "entry_price": pattern.entry_price if pattern.entry_price > 0 else pattern.details.get("mid_level", 0),
                    "stop_loss": pattern.stop_loss if pattern.stop_loss > 0 else pattern.invalidation_level,
                    "take_profit": pattern.take_profit if pattern.take_profit > 0 else 0
                },
                invalidation_level=pattern.invalidation_level,
                reason_codes=pattern.reason_codes,
                created_at=datetime.utcnow(),
                metadata=pattern.details
            )
            signals.append(signal)

        for structure in structures:
            if structure.direction == "neutral":
                continue

            signal = StandardPASignal(
                symbol=self._symbol,
                timeframe=self._timeframe,
                pattern=structure.pattern,
                direction=structure.direction,
                confidence_score=structure.confidence_score,
                quality_score=structure.quality_score,
                entry_context={
                    "structure_type": structure.structure_type if hasattr(structure, 'structure_type') else structure.pattern.value,
                    "level": structure.details.get("level", 0)
                },
                invalidation_level=structure.invalidation_level,
                reason_codes=structure.reason_codes,
                created_at=datetime.utcnow(),
                metadata=structure.details
            )
            signals.append(signal)

        return signals

    def _calculate_total_score(
        self,
        patterns: List[PatternAnalysis],
        structures: List[PatternAnalysis]
    ) -> Tuple[float, str]:
        """محاسبه امتیاز کل و تعیین جهت"""
        bullish_score = 0.0
        bearish_score = 0.0

        for pattern in patterns:
            weight = self.pattern_weights.get(pattern.pattern, 1.0)
            score = pattern.confidence_score * weight / 100 * 20

            if pattern.direction == "bullish":
                bullish_score += score
            elif pattern.direction == "bearish":
                bearish_score += score

        for structure in structures:
            weight = self.pattern_weights.get(structure.pattern, 1.0)
            score = structure.confidence_score * weight / 100 * 15

            if structure.direction == "bullish":
                bullish_score += score
            elif structure.direction == "bearish":
                bearish_score += score

        total_score = max(bullish_score, bearish_score)

        # تعیین جهت
        if bullish_score > bearish_score * 1.3:
            direction = "bullish"
        elif bearish_score > bullish_score * 1.3:
            direction = "bearish"
        else:
            direction = "neutral"

        return min(total_score, 100), direction

    def _extract_key_levels(
        self,
        candles: List[CandleData],
        patterns: List[PatternAnalysis],
        structures: List[PatternAnalysis]
    ) -> Dict[str, List[float]]:
        """استخراج سطوح کلیدی"""
        supports = []
        resistances = []

        # از الگوها
        for pattern in patterns:
            if pattern.direction == "bullish":
                if pattern.invalidation_level > 0:
                    supports.append(pattern.invalidation_level)
            elif pattern.direction == "bearish":
                if pattern.invalidation_level > 0:
                    resistances.append(pattern.invalidation_level)

            # Wick levels
            wick_level = pattern.details.get("wick_level")
            if wick_level:
                if pattern.direction == "bullish":
                    supports.append(wick_level)
                else:
                    resistances.append(wick_level)

        # از ساختارها
        for structure in structures:
            level = structure.details.get("level", 0)
            if level > 0:
                if structure.direction == "bullish":
                    resistances.append(level)  # broken resistance
                else:
                    supports.append(level)  # broken support

        # از کندل‌های اخیر
        if len(candles) >= 20:
            recent = candles[-20:]
            recent_high = max(c.high for c in recent)
            recent_low = min(c.low for c in recent)
            resistances.append(recent_high)
            supports.append(recent_low)

        return {
            "supports": sorted(set(supports), reverse=True)[:5],
            "resistances": sorted(set(resistances), reverse=True)[:5]
        }

    def _get_empty_result(self) -> "PriceActionResult":
        """ایجاد نتیجه خالی"""
        return PriceActionResult(
            symbol=self._symbol,
            timeframe=self._timeframe,
            total_score=0,
            direction="neutral",
            context=MarketContext(),
            patterns=[],
            structures=[],
            standard_signals=[],
            key_levels={"supports": [], "resistances": []},
            details={"error": "Insufficient data"}
        )


# =====================================================
# نتیجه تحلیل Price Action
# =====================================================

@dataclass
class PriceActionResult:
    """
    نتیجه کامل تحلیل Price Action

    خروجی استاندارد برای مصرف توسط Decision Engine.
    """
    symbol: str
    timeframe: str
    total_score: float
    direction: str
    context: MarketContext
    patterns: List[PatternAnalysis]
    structures: List[PatternAnalysis]
    standard_signals: List[StandardPASignal]
    key_levels: Dict[str, List[float]]
    details: Dict[str, Any] = field(default_factory=dict)

    def get_entry_signals(
        self,
        min_confidence: float = 60.0
    ) -> List[StandardPASignal]:
        """
        دریافت سیگنال‌های ورود با حداقل اعتماد

        Args:
            min_confidence: حداقل امتیاز اعتماد

        Returns:
            لیست سیگنال‌های qualified
        """
        return [
            s for s in self.standard_signals
            if s.confidence_score >= min_confidence
            and s.direction != "neutral"
        ]

    def get_strongest_signal(self) -> Optional[StandardPASignal]:
        """دریافت قوی‌ترین سیگنال"""
        if not self.standard_signals:
            return None

        return max(
            self.standard_signals,
            key=lambda s: s.confidence_score * (1 + s.quality_score / 200)
        )

    def to_dict(self) -> Dict[str, Any]:
        """تبدیل به دیکشنری"""
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "total_score": self.total_score,
            "direction": self.direction,
            "patterns_detected": len(self.patterns),
            "structures_detected": len(self.structures),
            "signals": [s.to_dict() for s in self.standard_signals],
            "key_levels": self.key_levels,
            "details": self.details
        }
