"""
موتور Smart Money Concept

این موتور تحلیل جامع SMC را انجام می‌دهد:
- ساختار بازار (BOS, CHOCH, MSS)
- Swing High / Swing Low
- نقدینگی و Liquidity Sweep
- Order Blocks (OB, MB, BB, RB)
- Fair Value Gap (FVG, IFVG)
- Premium/Discount/Equilibrium
- Session Liquidity و Kill Zones

خروجی استاندارد برای Decision Engine

نویسنده: MT5 Trading Team
تاریخ: 2026-06-14
ورژن: 2.0.0
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from ..core.enums import (
    MarketStructure, BlockType, BlockStatus, FVGType,
    LiquidityType, TradingSession, TrendDirection
)
from ..core.logger import get_logger
from ..core.config import settings

logger = get_logger("smc_engine")


# =====================================================
# ساختارهای داده
# =====================================================

@dataclass
class SwingLevel:
    """
    سطح سوئینگ (سقف یا کف)

    یک نقطه پیوت در ساختار بازار که به عنوان سطح کلیدی عمل می‌کند.

    Attributes:
        level_type: نوع سوئینگ (swing_high یا swing_low)
        price: قیمت سطح
        candle_time: زمان کندل
        candle_index: ایندکس کندل در آرایه
        is_broken: آیا شکسته شده
        break_time: زمان شکست
        break_price: قیمت شکست
        strength: قدرت سوئینگ (تست‌های موفق)
    """
    level_type: str  # swing_high, swing_low
    price: float
    candle_time: datetime
    candle_index: int
    is_broken: bool = False
    break_time: Optional[datetime] = None
    break_price: float = 0.0
    strength: float = 1.0


@dataclass
class StructureEvent:
    """
    رویداد ساختار بازار

    هر رویداد BOS, CHOCH, یا MSS یک StructureEvent ایجاد می‌کند.

    Attributes:
        event_type: نوع رویداد (BOS, CHOCH, MSS)
        direction: جهت رویداد (bullish, bearish)
        level: سطح شکسته شده
        candle_time: زمان کندل
        candle_index: ایندکس کندل
        is_valid: آیا رویداد معتبر است
        score: امتیاز رویداد
        confirmation_count: تعداد تأییدیه‌ها
    """
    event_type: MarketStructure
    direction: TrendDirection
    level: float
    candle_time: datetime
    candle_index: int
    is_valid: bool = True
    score: float = 0.0
    confirmation_count: int = 0


@dataclass
class BlockZone:
    """
    ناحیه بلاک (OB, MB, BB, RB)

    بلاک‌ها نواحی هستند که نقدینگیinstitutional در آن‌ها حضور دارد.

    Attributes:
        block_type: نوع بلاک (order_block, mitigation_block, breaker_block, rejection_block)
        direction: جهت بلاک (bullish, bearish)
        high: سقف بلاک
        low: کف بلاک
        mid: میانگین بلاک
        body_high: سقف بدنه کندل
        body_low: کف بدنه کندل
        created_at: زمان ایجاد
        created_index: ایندکس ایجاد
        status: وضعیت بلاک
        test_count: تعداد تست‌ها
        respect_count: تعداد ریسپکت‌ها
        score: امتیاز بلاک
        impulse_candles: تعداد کندل‌های ایمپالس
        origin_structure: رفرنس به ساختار مبدأ
    """
    block_type: BlockType
    direction: TrendDirection
    high: float
    low: float
    mid: float
    body_high: float
    body_low: float
    created_at: datetime
    created_index: int
    status: BlockStatus = BlockStatus.ACTIVE
    test_count: int = 0
    respect_count: int = 0
    score: float = 0.0
    impulse_candles: int = 0
    origin_structure: Optional[str] = None


@dataclass
class FVGZone:
    """
    ناحیه Fair Value Gap

    FVG گپ‌های قیمتی هستند که ناشی از عدم تعادل عرضه و تقاضا می‌باشند.

    Attributes:
        fvg_type: نوع FVG (bullish_fvg, bearish_fvg, ifvg)
        high: سقف FVG
        low: کف FVG
        mid: میانه FVG (نقطه 50%)
        size_pips: اندازه FVG به پیپ
        created_at: زمان ایجاد
        created_index: ایندکس ایجاد
        fill_percent: درصد پر شدن
        status: وضعیت (unfilled, partial, filled)
        is_ifvg: آیا IFVG است (Inverse FVG)
        origin_block: بلاک مبدأ (برای IFVG)
    """
    fvg_type: FVGType
    high: float
    low: float
    mid: float
    size_pips: float
    created_at: datetime
    created_index: int
    fill_percent: float = 0.0
    status: str = "unfilled"
    is_ifvg: bool = False
    origin_block: Optional[str] = None


@dataclass
class LiquidityLevel:
    """
    سطح نقدینگی

    سطوحی که نقدینگی معاملاتی در آن‌ها متمرکز است.

    Attributes:
        liquidity_type: نوع نقدینگی
        level: قیمت سطح
        created_at: زمان ایجاد
        is_swept: آیا اسویپ شده
        sweep_time: زمان اسویپ
        sweep_type: نوع اسویپ (wick, impulse)
        sweep_candle: ایندکس کندل اسویپ
        retest_count: تعداد ری‌تست‌ها
    """
    liquidity_type: LiquidityType
    level: float
    created_at: datetime
    is_swept: bool = False
    sweep_time: Optional[datetime] = None
    sweep_type: Optional[str] = None
    sweep_candle: Optional[int] = None
    retest_count: int = 0


@dataclass
class SessionLiquidity:
    """
    نقدینگی سشن

    نقدینگی متمرکز در هر سشن معاملاتی.

    Attributes:
        session: نام سشن
        high_liq: سطح نقدینگی بالا
        low_liq: سطح نقدینگی پایین
        open_time: زمان شروع
        is_swept_high: آیا نقدینگی بالا اسویپ شده
        is_swept_low: آیا نقدینگی پایین اسویپ شده
    """
    session: TradingSession
    high_liq: float
    low_liq: float
    open_time: datetime
    is_swept_high: bool = False
    is_swept_low: bool = False


@dataclass
class SMCResult:
    """
    نتیجه تحلیل SMC

    خروجی استاندارد که شامل تمام نتایج تحلیل است.

    Attributes:
        total_score: امتیاز کل (0-100)
        trend: جهت روند فعلی
        trend_strength: قدرت روند (0-100)
        last_structure_event: آخرین رویداد ساختار
        liquidity_swept: آیا نقدینگی اسویپ شده
        sweep_direction: جهت اسویپ
        active_blocks: بلاک‌های فعال
        active_fvgs: FVGهای فعال
        premium_discount: وضعیت قیمتی (premium, discount, equilibrium)
        equilibrium_zone: ناحیه تعادل
        session_score: امتیاز سشن
        killzone_active: آیا Kill Zone فعال است
        active_killzones: سشن‌های Kill Zone فعال
        session_liquidity: نقدینگی سشن
        internal_liquidity: نقدینگی داخلی
        details: جزئیات کامل
    """
    total_score: float
    trend: TrendDirection
    trend_strength: float
    last_structure_event: Optional[StructureEvent]
    liquidity_swept: bool
    sweep_direction: Optional[str]
    active_blocks: List[BlockZone]
    active_fvgs: List[FVGZone]
    premium_discount: str
    equilibrium_zone: Tuple[float, float]
    session_score: float
    killzone_active: bool
    active_killzones: List[str]
    session_liquidity: List[SessionLiquidity]
    internal_liquidity: List[LiquidityLevel]
    details: Dict[str, Any] = field(default_factory=dict)


# =====================================================
# تحلیلگر ساختار بازار
# =====================================================

class MarketStructureAnalyzer:
    """
    تحلیلگر ساختار بازار

    تشخیص دقیق:
    - Swing High / Swing Low (با قدرت‌سنجی)
    - BOS (Break of Structure) - شکست در جهت روند
    - CHOCH (Change of Character) - تغییر شخصیت روند
    - MSS (Market Structure Shift) - تغییر ساختار کامل

    متدولوژی:
    - سوئینگ با lookback پویا تشخیص داده می‌شود
    - BOS = شکست سوئینگ در جهت روند فعلی
    - CHOCH = شکست سوئینگ خلاف جهت روند (اولین نشانه تغییر)
    - MSS = CHOCH + BOS در جهت جدید (تأیید تغییر)

    امتیازدهی:
    - BOS: 8 امتیاز (تأیید روند)
    - CHOCH: 6 امتیاز (هشدار تغییر)
    - MSS: 12 امتیاز (تأیید تغییر)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات شامل:
                - swing_lookback: تعداد کندل برای تشخیص سوئینگ (default: 5)
                - bos_buffer: بافر برای تأیید شکست (default: 0.0001)
                - require_close: آیا نیاز به کلوز برای تأیید (default: True)
                - min_swing_strength: حداقل قدرت سوئینگ (default: 1.0)
        """
        config = config or {}
        self.swing_lookback = config.get("swing_lookback", 5)
        self.bos_buffer = config.get("bos_buffer", 0.0001)
        self.require_close = config.get("require_close", True)
        self.min_swing_strength = config.get("min_swing_strength", 1.0)

        # وضعیت داخلی
        self.swing_highs: List[SwingLevel] = []
        self.swing_lows: List[SwingLevel] = []
        self.structure_events: List[StructureEvent] = []
        self.current_trend: TrendDirection = TrendDirection.NEUTRAL
        self.trend_strength: float = 0.0
        self.last_event: Optional[StructureEvent] = None
        self.score: float = 0.0

        # ردیابی ساختار
        self.higher_highs: List[float] = []
        self.higher_lows: List[float] = []
        self.lower_highs: List[float] = []
        self.lower_lows: List[float] = []

        logger.debug("MarketStructureAnalyzer مقداردهی شد")

    def analyze(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ) -> Dict[str, Any]:
        """
        تحلیل کامل ساختار بازار

        پروسه تحلیل:
        1. تشخیص تمام نقاط سوئینگ
        2. تشخیص رویدادهای ساختار (BOS, CHOCH, MSS)
        3. به‌روزرسانی وضعیت روند
        4. محاسبه قدرت روند
        5. تشخیص الگوهای HH/HL/LH/LL

        Args:
            highs: آرایه سقف‌ها (numpy)
            lows: آرایه کف‌ها (numpy)
            closes: آرایه قیمت‌های بسته (numpy)
            times: لیست زمان‌ها

        Returns:
            دیکشنری شامل:
                - trend: جهت روند
                - score: امتیاز ساختار
                - last_event: آخرین رویداد
                - swing_highs: لیست سقف‌های سوئینگ
                - swing_lows: لیست کف‌های سوئینگ
                - key_levels: سطوح کلیدی
                - structure_pattern: الگوی ساختار
                - trend_strength: قدرت روند
        """
        logger.debug("شروع تحلیل ساختار بازار")

        # مرحله 1: تشخیص سوئینگ‌ها
        self._detect_swings(highs, lows, times)

        # مرحله 2: تشخیص رویدادهای ساختار
        self._detect_structure_events(highs, lows, closes, times)

        # مرحله 3: به‌روزرسانی روند
        self._update_trend()

        # مرحله 4: تشخیص الگوی ساختار
        self._detect_structure_pattern()

        # مرحله 5: محاسبه قدرت روند
        self._calculate_trend_strength()

        # مرحله 6: محاسبه امتیاز
        self._calculate_score()

        # دریافت سطوح کلیدی
        levels = self._get_key_levels()

        logger.info(
            f"تحلیل ساختار کامل شد | روند: {self.current_trend.value} | "
            f"امتیاز: {self.score:.1f} | قدرت: {self.trend_strength:.1f}"
        )

        return {
            "trend": self.current_trend.value,
            "trend_strength": self.trend_strength,
            "score": self.score,
            "last_event": {
                "type": self.last_event.event_type.value if self.last_event else None,
                "direction": self.last_event.direction.value if self.last_event else None,
                "level": self.last_event.level if self.last_event else None,
                "time": self.last_event.candle_time.isoformat() if self.last_event else None,
                "score": self.last_event.score if self.last_event else None
            } if self.last_event else None,
            "swing_highs": [
                {"price": s.price, "time": s.candle_time.isoformat(), "strength": s.strength}
                for s in self.swing_highs[-10:]
            ],
            "swing_lows": [
                {"price": s.price, "time": s.candle_time.isoformat(), "strength": s.strength}
                for s in self.swing_lows[-10:]
            ],
            "key_levels": levels,
            "structure_pattern": self._get_structure_pattern(),
            "recent_events": [
                {
                    "type": e.event_type.value,
                    "direction": e.direction.value,
                    "level": e.level,
                    "time": e.candle_time.isoformat()
                }
                for e in self.structure_events[-5:]
            ]
        }

    def _detect_swings(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص نقاط سوئینگ با الگوریتم فرکتال

        Swing High: سقفی که از L کندل قبل و بعد بالاتر است
        Swing Low: کفی که از L کندل قبل و بعد پایین‌تر است

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            times: لیست زمان‌ها
        """
        n = len(highs)
        lookback = self.swing_lookback

        if n < lookback * 2 + 1:
            logger.warning(f"داده کافی برای تشخیص سوئینگ نیست: {n} کندل")
            return

        swings_detected = 0

        for i in range(lookback, n - lookback):
            # تشخیص Swing High
            is_swing_high = self._is_swing_high(highs, i, lookback)
            if is_swing_high:
                self._add_swing_high(highs[i], times[i], i, highs, lows)
                swings_detected += 1

            # تشخیص Swing Low
            is_swing_low = self._is_swing_low(lows, i, lookback)
            if is_swing_low:
                self._add_swing_low(lows[i], times[i], i, highs, lows)
                swings_detected += 1

        logger.debug(f"{swings_detected} سوئینگ شناسایی شد")

    def _is_swing_high(self, highs: np.ndarray, index: int, lookback: int) -> bool:
        """
        بررسی اینکه آیا ایندکس یک سقف سوئینگ است

        Args:
            highs: آرایه سقف‌ها
            index: ایندکس مورد بررسی
            lookback: تعداد کندل‌های طرفین

        Returns:
            bool: True اگر سوئینگ باشد
        """
        current_high = highs[index]

        # بررسی طرف چپ
        for j in range(1, lookback + 1):
            if current_high <= highs[index - j]:
                return False

        # بررسی طرف راست
        for j in range(1, lookback + 1):
            if current_high <= highs[index + j]:
                return False

        return True

    def _is_swing_low(self, lows: np.ndarray, index: int, lookback: int) -> bool:
        """
        بررسی اینکه آیا ایندکس یک کف سوئینگ است

        Args:
            lows: آرایه کف‌ها
            index: ایندکس مورد بررسی
            lookback: تعداد کندل‌های طرفین

        Returns:
            bool: True اگر سوئینگ باشد
        """
        current_low = lows[index]

        # بررسی طرف چپ
        for j in range(1, lookback + 1):
            if current_low >= lows[index - j]:
                return False

        # بررسی طرف راست
        for j in range(1, lookback + 1):
            if current_low >= lows[index + j]:
                return False

        return True

    def _add_swing_high(
        self,
        price: float,
        time: datetime,
        index: int,
        highs: np.ndarray,
        lows: np.ndarray
    ):
        """
        افزودن سقف سوئینگ با محاسبه قدرت

        قدرت سوئینگ بر اساس:
        - تعداد سوئینگ‌های کوچک‌تر حول آن
        - فاصله از میانگین

        Args:
            price: قیمت سوئینگ
            time: زمان
            index: ایندکس
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
        """
        # بررسی duplicate
        if self.swing_highs and abs(self.swing_highs[-1].candle_index - index) < 3:
            # اگر سوئینگ جدید قوی‌تر است، جایگزین کن
            if price > self.swing_highs[-1].price:
                self.swing_highs[-1] = SwingLevel(
                    level_type="swing_high",
                    price=price,
                    candle_time=time,
                    candle_index=index,
                    strength=self._calculate_swing_strength(index, highs, lows, "high")
                )
                logger.debug(f"Swing High به‌روزرسانی شد: {price:.5f}")
            return

        strength = self._calculate_swing_strength(index, highs, lows, "high")

        self.swing_highs.append(SwingLevel(
            level_type="swing_high",
            price=price,
            candle_time=time,
            candle_index=index,
            strength=strength
        ))

        # نگه داشتن آخرین 100 سوئینگ
        if len(self.swing_highs) > 100:
            self.swing_highs = self.swing_highs[-100:]

        logger.debug(f"Swing High شناسایی شد: {price:.5f} (قدرت: {strength:.1f})")

    def _add_swing_low(
        self,
        price: float,
        time: datetime,
        index: int,
        highs: np.ndarray,
        lows: np.ndarray
    ):
        """
        افزودن کف سوئینگ با محاسبه قدرت

        Args:
            price: قیمت سوئینگ
            time: زمان
            index: ایندکس
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
        """
        # بررسی duplicate
        if self.swing_lows and abs(self.swing_lows[-1].candle_index - index) < 3:
            if price < self.swing_lows[-1].price:
                self.swing_lows[-1] = SwingLevel(
                    level_type="swing_low",
                    price=price,
                    candle_time=time,
                    candle_index=index,
                    strength=self._calculate_swing_strength(index, highs, lows, "low")
                )
                logger.debug(f"Swing Low به‌روزرسانی شد: {price:.5f}")
            return

        strength = self._calculate_swing_strength(index, highs, lows, "low")

        self.swing_lows.append(SwingLevel(
            level_type="swing_low",
            price=price,
            candle_time=time,
            candle_index=index,
            strength=strength
        ))

        if len(self.swing_lows) > 100:
            self.swing_lows = self.swing_lows[-100:]

        logger.debug(f"Swing Low شناسایی شد: {price:.5f} (قدرت: {strength:.1f})")

    def _calculate_swing_strength(
        self,
        index: int,
        highs: np.ndarray,
        lows: np.ndarray,
        swing_type: str
    ) -> float:
        """
        محاسبه قدرت سوئینگ

        قدرت بر اساس:
        - شدت رد شدن از سوئینگ‌های مجاور
        - اندازه کندل‌های حول سوئینگ

        Args:
            index: ایندکس سوئینگ
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            swing_type: نوع سوئینگ (high/low)

        Returns:
            float: قدرت سوئینگ (1-5)
        """
        lookback = min(5, index, len(highs) - index - 1)
        if lookback < 2:
            return 1.0

        strength = 1.0

        if swing_type == "high":
            # بررسی رد شدن از سقف‌های مجاور
            current_high = highs[index]
            for j in range(1, lookback + 1):
                # طرف چپ
                diff_left = current_high - highs[index - j]
                # طرف راست
                diff_right = current_high - highs[index + j]

                if diff_left > 0 and diff_right > 0:
                    avg_diff = (diff_left + diff_right) / 2
                    # نرمال‌سازی به PIAT
                    pip_value = 0.0001
                    strength += min(avg_diff / (pip_value * 50), 2.0)

        else:  # swing_low
            current_low = lows[index]
            for j in range(1, lookback + 1):
                diff_left = lows[index - j] - current_low
                diff_right = lows[index + j] - current_low

                if diff_left > 0 and diff_right > 0:
                    avg_diff = (diff_left + diff_right) / 2
                    pip_value = 0.0001
                    strength += min(avg_diff / (pip_value * 50), 2.0)

        return min(max(strength, 1.0), 5.0)

    def _detect_structure_events(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص رویدادهای ساختار (BOS, CHOCH, MSS)

        منطق:
        - BOS: شکست سوئینگ در جهت روند (تأیید ادامه)
        - CHOCH: شکست سوئینگ خلاف جهت روند (اولین نشانه تغییر)
        - MSS: CHOCH + BOS جدید (تأیید تغییر)

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(closes)
        buffer = self.bos_buffer
        min_strength = self.min_swing_strength

        # بررسی شکست هر سقف سوئینگ
        for swing in self.swing_highs:
            if swing.is_broken or swing.strength < min_strength:
                continue

            for i in range(swing.candle_index + 1, n):
                price_check = closes[i] if self.require_close else highs[i]

                if price_check > swing.price * (1 + buffer):
                    direction = TrendDirection.BULLISH

                    if self.current_trend == TrendDirection.BEARISH:
                        # CHOCH - تغییر روند از نزولی به صعودی
                        event_type = MarketStructure.CHOCH
                        self._add_choch(swing.price, times[i], i, direction, swing.strength)
                    else:
                        # BOS - ادامه روند صعودی
                        event_type = MarketStructure.BOS
                        self._add_bos(swing.price, times[i], i, direction, swing.strength)

                    swing.is_broken = True
                    swing.break_time = times[i]
                    swing.break_price = closes[i]
                    break

        # بررسی شکست هر کف سوئینگ
        for swing in self.swing_lows:
            if swing.is_broken or swing.strength < min_strength:
                continue

            for i in range(swing.candle_index + 1, n):
                price_check = closes[i] if self.require_close else lows[i]

                if price_check < swing.price * (1 - buffer):
                    direction = TrendDirection.BEARISH

                    if self.current_trend == TrendDirection.BULLISH:
                        # CHOCH - تغییر روند از صعودی به نزولی
                        self._add_choch(swing.price, times[i], i, direction, swing.strength)
                    else:
                        # BOS - ادامه روند نزولی
                        self._add_bos(swing.price, times[i], i, direction, swing.strength)

                    swing.is_broken = True
                    swing.break_time = times[i]
                    swing.break_price = closes[i]
                    break

        # بررسی MSS
        self._check_mss()

    def _add_bos(
        self,
        level: float,
        time: datetime,
        index: int,
        direction: TrendDirection,
        swing_strength: float = 1.0
    ):
        """
        افزودن رویداد BOS

        BOS = Break of Structure
        شکست در جهت روند فعلی = تأیید ادامه روند

        Args:
            level: سطح شکسته شده
            time: زمان
            index: ایندکس
            direction: جهت
            swing_strength: قدرت سوئینگ شکسته شده
        """
        # امتیاز بر اساس قدرت سوئینگ
        base_score = 8.0
        score = base_score * swing_strength

        event = StructureEvent(
            event_type=MarketStructure.BOS,
            direction=direction,
            level=level,
            candle_time=time,
            candle_index=index,
            score=min(score, 15.0),
            confirmation_count=1
        )

        self.structure_events.append(event)
        self.last_event = event

        logger.info(
            f"BOS {direction.value} در سطح {level:.5f} | "
            f"امتیاز: {score:.1f}"
        )

    def _add_choch(
        self,
        level: float,
        time: datetime,
        index: int,
        direction: TrendDirection,
        swing_strength: float = 1.0
    ):
        """
        افزودن رویداد CHOCH

        CHOCH = Change of Character
        شکست خلاف جهت روند = اولین نشانه تغییر

        بر خلاف pass قبلی، اینجا روند را به حالت NEUTRAL
        تغییر می‌دهیم تا منتظر تأیید MSS بمانیم

        Args:
            level: سطح شکسته شده
            time: زمان
            index: ایندکس
            direction: جهت جدید
            swing_strength: قدرت سوئینگ
        """
        base_score = 6.0
        score = base_score * swing_strength

        event = StructureEvent(
            event_type=MarketStructure.CHOCH,
            direction=direction,
            level=level,
            candle_time=time,
            candle_index=index,
            score=min(score, 12.0),
            confirmation_count=0
        )

        self.structure_events.append(event)
        self.last_event = event

        # CHOCH روند را به NEUTRAL تغییر می‌دهد
        # تا MSS تأیید نشود، روند جدید قطعی نیست
        self.current_trend = TrendDirection.NEUTRAL

        logger.info(
            f"CHOCH {direction.value} در سطح {level:.5f} | "
            f"روند به NEUTRAL تغییر کرد | امتیاز: {score:.1f}"
        )

    def _check_mss(self):
        """
        بررسی MSS (Market Structure Shift)

        MSS زمانی تشکیل می‌شود:
        1. یک CHOCH رخ داده
        2.続いて یک BOS در همان جهت جدید

        این ترکیب = تأیید تغییر روند قطعی

        MSS امتیاز بالاتری دارد (12-15) چون
        سیگنال معتبرتری برای ورود است.
        """
        if len(self.structure_events) < 2:
            return

        # بررسی آخرین دو رویداد
        recent = self.structure_events[-2:]

        # الگو: CHOCH بعد BOS در همان جهت
        if (recent[0].event_type == MarketStructure.CHOCH and
            recent[1].event_type == MarketStructure.BOS and
            recent[0].direction == recent[1].direction):

            # ایجاد MSS
            mss_score = 12.0 + recent[0].score * 0.5

            mss = StructureEvent(
                event_type=MarketStructure.MSS,
                direction=recent[0].direction,
                level=recent[1].level,
                candle_time=recent[1].candle_time,
                candle_index=recent[1].candle_index,
                score=min(mss_score, 20.0),
                confirmation_count=2
            )

            self.structure_events.append(mss)
            self.last_event = mss

            # MSS روند جدید را تأیید می‌کند
            self.current_trend = mss.direction
            self.trend_strength = 100.0

            logger.info(
                f"MSS {mss.direction.value} تأیید شد | "
                f"روند جدید: {mss.direction.value} | امتیاز: {mss_score:.1f}"
            )

    def _update_trend(self):
        """
        به‌روزرسانی جهت روند

        رویکرد محافظه‌کارانه:
        - BOS: ادامه روند فعلی
        - CHOCH: NEUTRAL (منتظر تأیید)
        - MSS: تغییر روند قطعی
        """
        if not self.last_event:
            return

        event_type = self.last_event.event_type
        event_direction = self.last_event.direction

        if event_type == MarketStructure.BOS:
            # BOS روند را تأیید می‌کند
            self.current_trend = event_direction
            logger.debug(f"روند تأیید شد: {event_direction.value}")

        elif event_type == MarketStructure.MSS:
            # MSS روند جدید را قطعی می‌کند
            self.current_trend = event_direction
            logger.debug(f"روند جدید قطعی: {event_direction.value}")

        # CHOCH در متد _add_choch هندل می‌شود (NEUTRAL)

    def _detect_structure_pattern(self):
        """
        تشخیص الگوی ساختار (HH, HL, LH, LL)

        الگوهای صعودی:
        - Higher High + Higher Low = روند صعودی قوی

        الگوهای نزولی:
        - Lower High + Lower Low = روند نزولی قوی
        """
        # پاک کردن لیست‌های قبلی
        self.higher_highs = []
        self.higher_lows = []
        self.lower_highs = []
        self.lower_lows = []

        # بررسی Higher Highs (صعودی)
        for i in range(1, min(len(self.swing_highs), 20)):
            current = self.swing_highs[-i]
            prev = self.swing_highs[-i-1] if i < len(self.swing_highs) else None
            if prev and current.price > prev.price:
                self.higher_highs.append(current.price)
            elif prev and current.price < prev.price:
                self.lower_highs.append(current.price)

        # بررسی Higher Lows (صعودی)
        for i in range(1, min(len(self.swing_lows), 20)):
            current = self.swing_lows[-i]
            prev = self.swing_lows[-i-1] if i < len(self.swing_lows) else None
            if prev and current.price > prev.price:
                self.higher_lows.append(current.price)
            elif prev and current.price < prev.price:
                self.lower_lows.append(current.price)

    def _get_structure_pattern(self) -> str:
        """
        دریافت الگوی ساختار فعلی

        Returns:
            str: شامل "higher_highs", "lower_lows", "ranging", etc.
        """
        if len(self.higher_highs) >= 2 and len(self.higher_lows) >= 2:
            return "higher_highs_higher_lows"
        elif len(self.lower_highs) >= 2 and len(self.lower_lows) >= 2:
            return "lower_highs_lower_lows"
        elif len(self.higher_highs) >= 2:
            return "higher_highs"
        elif len(self.lower_lows) >= 2:
            return "lower_lows"
        else:
            return "ranging"

    def _calculate_trend_strength(self):
        """
        محاسبه قدرت روند

        عوامل مؤثر:
        - تعداد BOS در جهت روند
        - نسبت HH/HL به LH/LL
        - قدرت سوئینگ‌های اخیر
        """
        if self.current_trend == TrendDirection.NEUTRAL:
            self.trend_strength = 0.0
            return

        strength = 50.0  # پایه

        if self.current_trend == TrendDirection.BULLISH:
            # BOSهای صعودی
            bullish_bos = len([e for e in self.structure_events[-10:]
                              if e.event_type == MarketStructure.BOS
                              and e.direction == TrendDirection.BULLISH])
            strength += bullish_bos * 10

            # نسبت HH به LH
            if self.lower_highs:
                strength -= len(self.lower_highs) * 5
            if self.higher_highs:
                strength += len(self.higher_highs) * 5

        else:  # BEARISH
            bearish_bos = len([e for e in self.structure_events[-10:]
                              if e.event_type == MarketStructure.BOS
                              and e.direction == TrendDirection.BEARISH])
            strength += bearish_bos * 10

            if self.lower_lows:
                strength += len(self.lower_lows) * 5
            if self.higher_lows:
                strength -= len(self.higher_lows) * 5

        self.trend_strength = min(max(strength, 0.0), 100.0)

    def _calculate_score(self):
        """
        محاسبه امتیاز نهایی ساختار

        امتیاز 0-15 برای تحلیل کلی
        """
        if not self.last_event:
            self.score = 0.0
            return

        base_scores = {
            MarketStructure.BOS: 8,
            MarketStructure.CHOCH: 6,
            MarketStructure.MSS: 12
        }

        base = base_scores.get(self.last_event.event_type, 0)

        # تشدید با قدرت روند
        if self.current_trend != TrendDirection.NEUTRAL:
            base += self.trend_strength * 0.03

        self.score = min(base, 15.0)

    def _get_key_levels(self) -> Dict[str, Any]:
        """
        دریافت سطوح کلیدی برای تحلیل

        Returns:
            Dict شامل:
                - last_swing_high: آخرین سقف سوئینگ
                - last_swing_low: آخرین کف سوئینگ
                - unbroken_high: آخرین سقف شکسته نشده
                - unbroken_low: آخرین کف شکسته نشده
                - range_high: بالاترین سوئینگ اخیر
                - range_low: پایین‌ترین سوئینگ اخیر
        """
        levels = {}

        # آخرین سقف سوئینگ
        unbroken_highs = [s for s in self.swing_highs if not s.is_broken]
        if unbroken_highs:
            levels["unbroken_high"] = unbroken_highs[-1].price
            levels["unbroken_high_strength"] = unbroken_highs[-1].strength
        elif self.swing_highs:
            levels["last_swing_high"] = self.swing_highs[-1].price

        # آخرین کف سوئینگ
        unbroken_lows = [s for s in self.swing_lows if not s.is_broken]
        if unbroken_lows:
            levels["unbroken_low"] = unbroken_lows[-1].price
            levels["unbroken_low_strength"] = unbroken_lows[-1].strength
        elif self.swing_lows:
            levels["last_swing_low"] = self.swing_lows[-1].price

        # محدوده رنج
        recent_highs = self.swing_highs[-20:] if len(self.swing_highs) >= 20 else self.swing_highs
        recent_lows = self.swing_lows[-20:] if len(self.swing_lows) >= 20 else self.swing_lows

        if recent_highs:
            levels["range_high"] = max(s.price for s in recent_highs)
        if recent_lows:
            levels["range_low"] = min(s.price for s in recent_lows)

        return levels


# =====================================================
# تحلیلگر نقدینگی
# =====================================================

class LiquidityAnalyzer:
    """
    تحلیلگر نقدینگی

    تشخیص:
    - Buy Side Liquidity (بالای سقف‌های سوئینگ)
    - Sell Side Liquidity (پایین کف‌های سوئینگ)
    - Internal Liquidity (بین سوئینگ‌ها)
    - External Liquidity (خارج از رنج)
    - Session Liquidity (سشن‌های معاملاتی)
    - Liquidity Sweep (اسویپ نقدینگی)

    انواع Sweep:
    - Wick Sweep: سایه می‌زند اما کلوز داخل می‌ماند (بهتر)
    - Impulse Sweep: کلوز خارج از سطح (ضعیف‌تر)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات شامل:
                - sweep_lookback: تعداد کندل برای بررسی اسویپ
                - min_sweep_wick: حداقل سایه برای wick sweep
        """
        config = config or {}
        self.sweep_lookback = config.get("sweep_lookback", 20)
        self.min_sweep_wick = config.get("min_sweep_wick", 0.0003)

        self.liquidity_levels: List[LiquidityLevel] = []
        self.session_liquidity: List[SessionLiquidity] = []
        self.internal_liquidity: List[LiquidityLevel] = []
        self.recent_sweep: Optional[LiquidityLevel] = None
        self.sweep_direction: Optional[str] = None
        self.score: float = 0.0

        logger.debug("LiquidityAnalyzer مقداردهی شد")

    def analyze(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime],
        swing_highs: List[SwingLevel],
        swing_lows: List[SwingLevel]
    ) -> Dict[str, Any]:
        """
        تحلیل کامل نقدینگی

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
            swing_highs: لیست سقف‌های سوئینگ
            swing_lows: لیست کف‌های سوئینگ

        Returns:
            Dict شامل نتایج تحلیل نقدینگی
        """
        logger.debug("شروع تحلیل نقدینگی")

        # تشخیص سطوح نقدینگی اصلی
        self._detect_liquidity_levels(swing_highs, swing_lows, times)

        # تشخیص نقدینگی داخلی
        self._detect_internal_liquidity(highs, lows, times)

        # تشخیص اسویپ
        self._detect_sweeps(highs, lows, closes, times)

        # محاسبه امتیاز
        self._calculate_score()

        logger.info(
            f"تحلیل نقدینگی کامل شد | امتیاز: {self.score:.1f} | "
            f"اسویپ: {self.recent_sweep is not None}"
        )

        return {
            "score": self.score,
            "liquidity_swept": self.recent_sweep is not None,
            "sweep_direction": self.sweep_direction,
            "sweep_type": self.recent_sweep.sweep_type if self.recent_sweep else None,
            "sweep_level": self.recent_sweep.level if self.recent_sweep else None,
            "sweep_time": self.recent_sweep.sweep_time.isoformat() if self.recent_sweep and self.recent_sweep.sweep_time else None,
            "available_buy_side": [
                {"level": l.level, "created": l.created_at.isoformat()}
                for l in self.liquidity_levels
                if l.liquidity_type == LiquidityType.BUY_SIDE and not l.is_swept
            ],
            "available_sell_side": [
                {"level": l.level, "created": l.created_at.isoformat()}
                for l in self.liquidity_levels
                if l.liquidity_type == LiquidityType.SELL_SIDE and not l.is_swept
            ],
            "internal_liquidity": [
                {"type": l.liquidity_type.value, "level": l.level}
                for l in self.internal_liquidity
            ],
            "recent_sweeps": [
                {
                    "type": l.liquidity_type.value,
                    "level": l.level,
                    "sweep_type": l.sweep_type,
                    "time": l.sweep_time.isoformat() if l.sweep_time else None
                }
                for l in self.liquidity_levels
                if l.is_swept
            ][-5:]
        }

    def _detect_liquidity_levels(
        self,
        swing_highs: List[SwingLevel],
        swing_lows: List[SwingLevel],
        times: List[datetime]
    ):
        """
        تشخیص سطوح نقدینگی اصلی

        Buy Side = بالای سقف‌های سوئینگ (استاپ لاس‌های shorts)
        Sell Side = پایین کف‌های سوئینگ (استاپ لاس‌های longs)

        Args:
            swing_highs: لیست سقف‌های سوئینگ
            swing_lows: لیست کف‌های سوئینگ
            times: لیست زمان‌ها
        """
        # Buy Side Liquidity
        for swing in swing_highs:
            existing = [l for l in self.liquidity_levels
                       if abs(l.level - swing.price) < swing.price * 0.0005]
            if not existing:
                liq_type = LiquidityType.BUY_SIDE
                if swing.strength >= 3.0:
                    liq_type = LiquidityType.EXTERNAL
                elif swing.strength <= 1.5:
                    liq_type = LiquidityType.INTERNAL

                self.liquidity_levels.append(LiquidityLevel(
                    liquidity_type=liq_type,
                    level=swing.price,
                    created_at=swing.candle_time
                ))

        # Sell Side Liquidity
        for swing in swing_lows:
            existing = [l for l in self.liquidity_levels
                       if abs(l.level - swing.price) < swing.price * 0.0005]
            if not existing:
                liq_type = LiquidityType.SELL_SIDE
                if swing.strength >= 3.0:
                    liq_type = LiquidityType.EXTERNAL
                elif swing.strength <= 1.5:
                    liq_type = LiquidityType.INTERNAL

                self.liquidity_levels.append(LiquidityLevel(
                    liquidity_type=liq_type,
                    level=swing.price,
                    created_at=swing.candle_time
                ))

        # محدود کردن
        if len(self.liquidity_levels) > 100:
            self.liquidity_levels = sorted(
                self.liquidity_levels,
                key=lambda x: x.created_at,
                reverse=True
            )[:100]

        logger.debug(
            f"{len(self.liquidity_levels)} سطح نقدینگی شناسایی شد"
        )

    def _detect_internal_liquidity(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص نقدینگی داخلی

        نقدینگی داخلی = سطوح با تعداد زیادی تست

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            times: لیست زمان‌ها
        """
        n = len(highs)
        if n < 20:
            return

        # پیدا کردن سطوح با تعداد زیادی برخورد
        # استفاده از الگوریتم clustering ساده
        all_levels = list(highs[-20:]) + list(lows[-20:])

        for level in all_levels:
            # شمارش برخوردها
            touches = 0
            for i in range(-20, 0):
                if abs(highs[i] - level) < level * 0.001:
                    touches += 1
                if abs(lows[i] - level) < level * 0.001:
                    touches += 1

            if touches >= 3:
                existing = [l for l in self.internal_liquidity
                           if abs(l.level - level) < level * 0.001]
                if not existing:
                    self.internal_liquidity.append(LiquidityLevel(
                        liquidity_type=LiquidityType.INTERNAL,
                        level=level,
                        created_at=times[-1]
                    ))

        if len(self.internal_liquidity) > 10:
            self.internal_liquidity = self.internal_liquidity[-10:]

    def _detect_sweeps(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص اسویپ نقدینگی

        Wick Sweep: قیمت می‌زند اما کلوز داخل می‌ماند (بهترین)
        Impulse Sweep: کلوز خارج از سطح

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(highs)
        lookback = min(self.sweep_lookback, n - 1)

        for liq in self.liquidity_levels:
            if liq.is_swept:
                continue

            # بررسی کندل‌های اخیر
            for i in range(max(0, n - lookback), n):
                if liq.liquidity_type in (LiquidityType.BUY_SIDE, LiquidityType.EXTERNAL):
                    # اسویپ بالایی
                    if highs[i] > liq.level:
                        # تشخیص نوع اسویپ
                        wick_size = highs[i] - max(closes[i], closes[i-1] if i > 0 else closes[i])
                        if closes[i] < liq.level and wick_size > self.min_sweep_wick:
                            sweep_type = "wick"
                        else:
                            sweep_type = "impulse"

                        liq.is_swept = True
                        liq.sweep_time = times[i]
                        liq.sweep_type = sweep_type
                        liq.sweep_candle = i
                        self.recent_sweep = liq
                        self.sweep_direction = "sell_side_hit"  # نقدینگی buy side گرفته شد

                        logger.info(
                            f"نقدینگی Buy Side اسویپ شد | "
                            f"سطح: {liq.level:.5f} | نوع: {sweep_type}"
                        )
                        break

                elif liq.liquidity_type in (LiquidityType.SELL_SIDE, LiquidityType.INTERNAL):
                    # اسویپ پایینی
                    if lows[i] < liq.level:
                        wick_size = min(closes[i], closes[i-1] if i > 0 else closes[i]) - lows[i]
                        if closes[i] > liq.level and wick_size > self.min_sweep_wick:
                            sweep_type = "wick"
                        else:
                            sweep_type = "impulse"

                        liq.is_swept = True
                        liq.sweep_time = times[i]
                        liq.sweep_type = sweep_type
                        liq.sweep_candle = i
                        self.recent_sweep = liq
                        self.sweep_direction = "buy_side_hit"  # نقدینگی sell side گرفته شد

                        logger.info(
                            f"نقدینگی Sell Side اسویپ شد | "
                            f"سطح: {liq.level:.5f} | نوع: {sweep_type}"
                        )
                        break

    def detect_session_liquidity(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        opens: np.ndarray,
        times: List[datetime],
        session: TradingSession
    ) -> SessionLiquidity:
        """
        تشخیص نقدینگی سشن

        هر سشن یک high و low مشخص دارد که
        نقدینگی در بالای high و پایین low متمرکز است.

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            opens: آرایه اوپن‌ها
            times: لیست زمان‌ها
            session: نوع سشن

        Returns:
            SessionLiquidity: اطلاعات نقدینگی سشن
        """
        # زمان سشن (ساعت UTC)
        session_hours = {
            TradingSession.SYDNEY: (22, 7),
            TradingSession.TOKYO: (0, 9),
            TradingSession.LONDON: (8, 17),
            TradingSession.NEW_YORK: (13, 22)
        }

        open_hour, close_hour = session_hours.get(session, (0, 24))

        # پیدا کردن کندل‌های سشن
        session_indices = []
        for i, t in enumerate(times):
            h = t.hour
            if open_hour < close_hour:
                if open_hour <= h < close_hour:
                    session_indices.append(i)
            else:  # سشن شبانه
                if h >= open_hour or h < close_hour:
                    session_indices.append(i)

        if not session_indices:
            logger.warning(f"هیچ کندلی برای سشن {session.value} یافت نشد")
            return SessionLiquidity(
                session=session,
                high_liq=0,
                low_liq=0,
                open_time=times[-1]
            )

        # سقف و کف سشن
        session_high = max(highs[i] for i in session_indices)
        session_low = min(lows[i] for i in session_indices)
        session_open_time = times[session_indices[0]]

        # بررسی اسویپ
        is_swept_high = any(highs[i] > session_high * 1.001 for i in session_indices)
        is_swept_low = any(lows[i] < session_low * 0.999 for i in session_indices)

        session_liq = SessionLiquidity(
            session=session,
            high_liq=session_high,
            low_liq=session_low,
            open_time=session_open_time,
            is_swept_high=is_swept_high,
            is_swept_low=is_swept_low
        )

        self.session_liquidity.append(session_liq)

        logger.debug(
            f"نقدینگی سشن {session.value} | "
            f"High: {session_high:.5f} | Low: {session_low:.5f}"
        )

        return session_liq

    def _calculate_score(self):
        """
        محاسبه امتیاز نقدینگی

        عوامل:
        - اسویپ اخیر: 12 امتیاز پایه
        - Wick sweep: +3 امتیاز
        - تعداد سطوح فعال: bonus
        """
        if not self.recent_sweep:
            self.score = 0.0
            return

        base_score = 12.0

        # Wick sweep بهتر است
        if self.recent_sweep.sweep_type == "wick":
            base_score += 3.0

        # تعداد سطوح فعال (نقدینگی باقی‌مانده)
        active_buy = len([l for l in self.liquidity_levels
                         if l.liquidity_type == LiquidityType.BUY_SIDE and not l.is_swept])
        active_sell = len([l for l in self.liquidity_levels
                          if l.liquidity_type == LiquidityType.SELL_SIDE and not l.is_swept])

        if active_buy > 0 and active_sell > 0:
            base_score += 2.0  # نقدینگی دو طرفه

        self.score = min(base_score, 20.0)


# =====================================================
# تحلیلگر بلاک‌ها
# =====================================================

class BlockAnalyzer:
    """
    تحلیلگر Order Blocks و انواع دیگر بلاک

    تشخیص:
    - Order Block (OB): کندل قبل از حرکت بزرگ
    - Mitigation Block (MB): ناحیه‌ای که MIT take می‌شود
    - Breaker Block (BB): بلاکی که شکسته شده و معکوس عمل می‌کند
    - Rejection Block (RB): بلاکی که قیمت را رد کرده

    الگوریتم تشخیص:
    1. کندل‌های کوچک (body < 40% range) را پیدا کن
    2. بررسی که بعد از آن حرکت بزرگ (impulse) داشته باشیم
    3. جهت حرکت → نوع بلاک (bullish/bearish)
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات شامل:
                - min_impulse_size: حداقل اندازه حرکت (default: 0.0020)
                - max_block_tests: حداکثر تست قبل از expire
                - block_expiry: روز تا انقضا
        """
        config = config or {}
        self.min_impulse_size = config.get("min_impulse_size", 0.0020)
        self.max_block_tests = config.get("max_block_tests", 3)
        self.block_expiry = config.get("block_expiry", 30)

        self.blocks: List[BlockZone] = []
        self.score: float = 0.0

        logger.debug("BlockAnalyzer مقداردهی شد")

    def analyze(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime],
        structure_events: List[StructureEvent] = None
    ) -> Dict[str, Any]:
        """
        تحلیل کامل بلاک‌ها

        Args:
            opens: آرایه اوپن‌ها
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
            structure_events: رویدادهای ساختار (اختیاری)

        Returns:
            Dict شامل نتایج تشخیص بلاک
        """
        logger.debug("شروع تحلیل بلاک‌ها")

        # تشخیص Order Blocks
        self._detect_order_blocks(opens, highs, lows, closes, times)

        # تشخیص Mitigation Blocks
        self._detect_mitigation_blocks(opens, highs, lows, closes, times)

        # تشخیص Breaker Blocks
        self._detect_breaker_blocks(highs, lows, closes, times)

        # تشخیص Rejection Blocks
        self._detect_rejection_blocks(opens, highs, lows, closes, times)

        # به‌روزرسانی وضعیت بلاک‌ها
        self._update_block_status(highs, lows, closes, times)

        # محاسبه امتیاز
        self._calculate_score()

        active_blocks = self._get_active_blocks()

        logger.info(
            f"تحلیل بلاک‌ها کامل شد | "
            f"فعال: {len(active_blocks)} | امتیاز: {self.score:.1f}"
        )

        return {
            "score": self.score,
            "active_blocks": [self._block_to_dict(b) for b in active_blocks],
            "bullish_blocks": [self._block_to_dict(b) for b in self.blocks
                              if b.direction == TrendDirection.BULLISH],
            "bearish_blocks": [self._block_to_dict(b) for b in self.blocks
                              if b.direction == TrendDirection.BEARISH],
            "block_summary": {
                "total": len(self.blocks),
                "active": len([b for b in self.blocks if b.status == BlockStatus.ACTIVE]),
                "tested": len([b for b in self.blocks if b.status == BlockStatus.TESTED]),
                "mitigated": len([b for b in self.blocks if b.status == BlockStatus.MITIGATED]),
                "broken": len([b for b in self.blocks if b.status == BlockStatus.BROKEN])
            }
        }

    def _detect_order_blocks(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص Order Block (OB)

        OB = کندل قبل از حرکت بزرگ
        - کندل کوچک (body < 40% range)
        - بعد از آن حرکت حداقل min_impulse_size

        Args:
            opens: آرایه اوپن‌ها
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(opens)
        min_impulse = self.min_impulse_size

        for i in range(3, n - 3):
            body = abs(closes[i] - opens[i])
            total_range = highs[i] - lows[i]

            if total_range == 0:
                continue

            body_ratio = body / total_range

            # کندل باید کوچک باشد (body < 40% range)
            if body_ratio > 0.4:
                continue

            # بررسی حرکت بعدی
            future_high = max(highs[i+1:i+4])
            future_low = min(lows[i+1:i+4])
            current_high = highs[i]
            current_low = lows[i]

            # Bullish OB
            bullish_impulse = future_high - current_high
            if bullish_impulse >= min_impulse:
                self._add_block(
                    block_type=BlockType.ORDER_BLOCK,
                    direction=TrendDirection.BULLISH,
                    high=current_high,
                    low=current_low,
                    body_high=max(opens[i], closes[i]),
                    body_low=min(opens[i], closes[i]),
                    time=times[i],
                    index=i,
                    impulse=bullish_impulse
                )

            # Bearish OB
            bearish_impulse = current_low - future_low
            if bearish_impulse >= min_impulse:
                self._add_block(
                    block_type=BlockType.ORDER_BLOCK,
                    direction=TrendDirection.BEARISH,
                    high=current_high,
                    low=current_low,
                    body_high=max(opens[i], closes[i]),
                    body_low=min(opens[i], closes[i]),
                    time=times[i],
                    index=i,
                    impulse=bearish_impulse
                )

    def _detect_mitigation_blocks(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص Mitigation Block (MB)

        MB = ناحیه‌ای که MIT take می‌شود
        معمولاً بعد از BOS/CHOCH ظاهر می‌شود

        Args:
            opens: آرایه اوپن‌ها
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(closes)

        for i in range(5, n - 5):
            # پیدا کردن کندل‌های با سایه بلند
            upper_wick = highs[i] - max(opens[i], closes[i])
            lower_wick = min(opens[i], closes[i]) - lows[i]
            body = abs(closes[i] - opens[i])
            total_range = highs[i] - lows[i]

            if total_range == 0:
                continue

            # MB: سایه بلند + بدنه نسبتاً کوچک
            if upper_wick > body * 2 and lower_wick < body * 0.5:
                # MB صعودی - فتیله بالا
                if closes[i] < opens[i]:  # نزولی
                    # بررسی واکنش بعدی
                    if i + 3 < n and closes[i+3] > highs[i]:
                        self._add_block(
                            block_type=BlockType.MITIGATION_BLOCK,
                            direction=TrendDirection.BULLISH,
                            high=highs[i],
                            low=lows[i],
                            body_high=max(opens[i], closes[i]),
                            body_low=min(opens[i], closes[i]),
                            time=times[i],
                            index=i,
                            impulse=0
                        )

            if lower_wick > body * 2 and upper_wick < body * 0.5:
                # MB نزولی - فتیله پایین
                if closes[i] > opens[i]:  # صعودی
                    if i + 3 < n and closes[i+3] < lows[i]:
                        self._add_block(
                            block_type=BlockType.MITIGATION_BLOCK,
                            direction=TrendDirection.BEARISH,
                            high=highs[i],
                            low=lows[i],
                            body_high=max(opens[i], closes[i]),
                            body_low=min(opens[i], closes[i]),
                            time=times[i],
                            index=i,
                            impulse=0
                        )

    def _detect_breaker_blocks(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص Breaker Block (BB)

        BB = Order Block شکسته شده که حالا معکوس عمل می‌کند
        Bullish OB شکسته شده → Bearish BB

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(closes)

        for block in self.blocks:
            if block.block_type != BlockType.ORDER_BLOCK:
                continue

            if block.status != BlockStatus.BROKEN:
                continue

            # تبدیل به Breaker Block
            breaker_direction = (
                TrendDirection.BEARISH if block.direction == TrendDirection.BULLISH
                else TrendDirection.BULLISH
            )

            self._add_block(
                block_type=BlockType.BREAKER_BLOCK,
                direction=breaker_direction,
                high=block.high,
                low=block.low,
                body_high=block.body_high,
                body_low=block.body_low,
                time=block.created_at,
                index=block.created_index,
                impulse=0
            )

            logger.debug(
                f"Breaker Block ایجاد شد | "
                f"جهت: {breaker_direction.value}"
            )

    def _detect_rejection_blocks(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص Rejection Block (RB)

        RB = ناحیه‌ای که قیمت به شدت رد کرده
        معمولاً با کندل‌های Rejective

        Args:
            opens: آرایه اوپن‌ها
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(closes)

        for i in range(3, n - 3):
            body = abs(closes[i] - opens[i])
            total_range = highs[i] - lows[i]

            if total_range == 0 or body == 0:
                continue

            # کندل Rejective: بدنه بزرگ + سایه کوتاه
            if body / total_range > 0.7:
                # Rejection Block صعودی
                if closes[i] > opens[i]:  # صعودی
                    if lows[i-1] > lows[i] and lows[i-2] > lows[i]:
                        # واکنش از کف
                        self._add_block(
                            block_type=BlockType.REJECTION_BLOCK,
                            direction=TrendDirection.BULLISH,
                            high=highs[i],
                            low=lows[i],
                            body_high=closes[i],
                            body_low=opens[i],
                            time=times[i],
                            index=i,
                            impulse=0
                        )

                # Rejection Block نزولی
                else:  # نزولی
                    if highs[i-1] < highs[i] and highs[i-2] < highs[i]:
                        # واکنش از سقف
                        self._add_block(
                            block_type=BlockType.REJECTION_BLOCK,
                            direction=TrendDirection.BEARISH,
                            high=highs[i],
                            low=lows[i],
                            body_high=opens[i],
                            body_low=closes[i],
                            time=times[i],
                            index=i,
                            impulse=0
                        )

    def _add_block(
        self,
        block_type: BlockType,
        direction: TrendDirection,
        high: float,
        low: float,
        body_high: float,
        body_low: float,
        time: datetime,
        index: int,
        impulse: float
    ):
        """
        افزودن بلاک جدید با بررسی duplicate

        Args:
            block_type: نوع بلاک
            direction: جهت
            high: سقف
            low: کف
            body_high: سقف بدنه
            body_low: کف بدنه
            time: زمان
            index: ایندکس
            impulse: اندازه ایمپالس
        """
        # بررسی duplicate (فاصله کمتر از 10 پیپ)
        for existing in self.blocks:
            if (existing.direction == direction and
                abs(existing.high - high) < 0.001 and
                abs(existing.low - low) < 0.001 and
                existing.block_type == block_type):
                return

        block = BlockZone(
            block_type=block_type,
            direction=direction,
            high=high,
            low=low,
            mid=(high + low) / 2,
            body_high=body_high,
            body_low=body_low,
            created_at=time,
            created_index=index,
            impulse_candles=1 if impulse > 0 else 0
        )

        # امتیاز اولیه
        if impulse > 0:
            block.score = min(10 + impulse * 1000, 15.0)

        self.blocks.append(block)

        if len(self.blocks) > 50:
            self.blocks = self.blocks[-50:]

        logger.debug(
            f"{block_type.value} {direction.value} اضافه شد | "
            f"محدوده: {low:.5f} - {high:.5f}"
        )

    def _update_block_status(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        به‌روزرسانی وضعیت بلاک‌ها

        وضعیت‌ها:
        - ACTIVE: هنوز تست نشده
        - TESTED: حداقل یک بار تست شده
        - MITIGATED: بخشی از نقدینگی گرفته شده
        - BROKEN: کاملاً شکسته شده
        - EXPIRED: منقضی شده (بیش از block_expiry روز)

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(highs)
        now = times[-1] if times else datetime.utcnow()

        for block in self.blocks:
            if block.status in (BlockStatus.BROKEN, BlockStatus.MITIGATED):
                continue

            # بررسی انقضا
            days_since_creation = (now - block.created_at).days
            if days_since_creation > self.block_expiry:
                block.status = BlockStatus.EXPIRED
                logger.debug(f"بلاک منقضی شد: {block.block_type.value}")
                continue

            # بررسی تست و شکست
            for i in range(block.created_index + 1, min(n, block.created_index + 50)):
                if block.direction == TrendDirection.BULLISH:
                    # بلاک صعودی
                    if lows[i] <= block.high and lows[i] >= block.low:
                        block.test_count += 1
                        block.status = BlockStatus.TESTED
                        if i + 1 < n and closes[i + 1] > block.high:
                            block.respect_count += 1
                            logger.debug(f"بلاک صعودی تست و ریسپکت شد")

                    elif closes[i] < block.low:
                        block.status = BlockStatus.BROKEN
                        logger.debug(f"بلاک صعودی شکسته شد")
                        break

                else:  # Bearish
                    if highs[i] >= block.low and highs[i] <= block.high:
                        block.test_count += 1
                        block.status = BlockStatus.TESTED
                        if i + 1 < n and closes[i + 1] < block.low:
                            block.respect_count += 1
                            logger.debug(f"بلاک نزولی تست و ریسپکت شد")

                    elif closes[i] > block.high:
                        block.status = BlockStatus.BROKEN
                        logger.debug(f"بلاک نزولی شکسته شد")
                        break

    def _calculate_score(self):
        """
        محاسبه امتیاز بلاک

        عوامل:
        - تعداد بلاک فعال
        - تعداد تست موفق
        - فاصله از قیمت فعلی
        """
        active = self._get_active_blocks()
        if not active:
            self.score = 0.0
            return

        max_score = 0

        for block in active:
            block_score = 0

            # امتیاز بر اساس نوع
            type_scores = {
                BlockType.ORDER_BLOCK: 10,
                BlockType.MITIGATION_BLOCK: 8,
                BlockType.BREAKER_BLOCK: 7,
                BlockType.REJECTION_BLOCK: 9
            }
            block_score = type_scores.get(block.block_type, 5)

            # تست موفق = امتیاز بیشتر
            if block.status == BlockStatus.TESTED and block.respect_count > 0:
                block_score += 3

            # تست کم = بهتر
            if block.test_count < 2:
                block_score += 2

            max_score = max(max_score, block_score)

        self.score = min(max_score, 15.0)

    def _get_active_blocks(self) -> List[BlockZone]:
        """دریافت بلاک‌های فعال"""
        return [b for b in self.blocks
                if b.status in (BlockStatus.ACTIVE, BlockStatus.TESTED)]

    def _block_to_dict(self, block: BlockZone) -> Dict:
        """تبدیل بلاک به دیکشنری"""
        return {
            "type": block.block_type.value,
            "direction": block.direction.value,
            "high": block.high,
            "low": block.low,
            "mid": block.mid,
            "body_high": block.body_high,
            "body_low": block.body_low,
            "status": block.status.value,
            "test_count": block.test_count,
            "respect_count": block.respect_count,
            "score": block.score,
            "created_at": block.created_at.isoformat()
        }


# =====================================================
# تحلیلگر FVG
# =====================================================

class FVGAnalyzer:
    """
    تحلیلگر Fair Value Gap

    تشخیص:
    - Bullish FVG: گپ صعودی بین Low کندل قبلی و High کندل بعدی
    - Bearish FVG: گپ نزولی بین High کندل قبلی و Low کندل بعدی
    - IFVG (Inverse FVG): FVG معکوس شده پس از تست

    FVG نشان‌دهنده عدم تعادل بازار است:
    - پر نشده = بازار به آن علاقه دارد
    - پر شده = نقدینگی گرفته شده
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات شامل:
                - min_fvg_size: حداقل اندازه FVG (default: 0.0005)
                - max_fvg_count: حداکثر FVG نگهداری
        """
        config = config or {}
        self.min_fvg_size = config.get("min_fvg_size", 0.0005)
        self.max_fvg_count = config.get("max_fvg_count", 30)

        self.fvgs: List[FVGZone] = []
        self.ifvgs: List[FVGZone] = []
        self.score: float = 0.0

        logger.debug("FVGAnalyzer مقداردهی شد")

    def analyze(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ) -> Dict[str, Any]:
        """
        تحلیل کامل FVG

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها

        Returns:
            Dict شامل نتایج تحلیل FVG
        """
        logger.debug("شروع تحلیل FVG")

        # تشخیص FVG معمولی
        self._detect_fvgs(highs, lows, times)

        # تشخیص IFVG (Inverse FVG)
        self._detect_ifvgs(highs, lows, closes, times)

        # بررسی پر شدن
        self._check_fills(highs, lows, times)

        # محاسبه امتیاز
        self._calculate_score()

        active_fvgs = self._get_active_fvgs()

        logger.info(
            f"تحلیل FVG کامل شد | "
            f"فعال: {len(active_fvgs)} | IFVG: {len(self.ifvgs)} | امتیاز: {self.score:.1f}"
        )

        return {
            "score": self.score,
            "active_fvgs": [self._fvg_to_dict(f) for f in active_fvgs],
            "active_ifvgs": [self._fvg_to_dict(f) for f in self.ifvgs if f.status != "filled"],
            "fvgs_summary": {
                "total": len(self.fvgs),
                "bullish": len([f for f in self.fvgs if f.fvg_type == FVGType.BULLISH]),
                "bearish": len([f for f in self.fvgs if f.fvg_type == FVGType.BEARISH]),
                "unfilled": len([f for f in self.fvgs if f.status == "unfilled"]),
                "partial": len([f for f in self.fvgs if f.status == "partial"]),
                "filled": len([f for f in self.fvgs if f.status == "filled"])
            }
        }

    def _detect_fvgs(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص FVG معمولی

        Bullish FVG: Low[i-1] > High[i+1]
        Bearish FVG: High[i-1] < Low[i+1]

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            times: لیست زمان‌ها
        """
        n = len(highs)

        for i in range(1, n - 1):
            # Bullish FVG
            # گپ بین Low کندل قبلی و High کندل بعدی
            if lows[i-1] > highs[i+1]:
                gap_size = lows[i-1] - highs[i+1]

                if gap_size >= self.min_fvg_size:
                    self.fvgs.append(FVGZone(
                        fvg_type=FVGType.BULLISH,
                        high=lows[i-1],
                        low=highs[i+1],
                        mid=(lows[i-1] + highs[i+1]) / 2,
                        size_pips=gap_size * 10000,
                        created_at=times[i],
                        created_index=i,
                        is_ifvg=False
                    ))

                    logger.debug(
                        f"Bullish FVG شناسایی شد | "
                        f"محدوده: {highs[i+1]:.5f} - {lows[i-1]:.5f}"
                    )

            # Bearish FVG
            if highs[i-1] < lows[i+1]:
                gap_size = lows[i+1] - highs[i-1]

                if gap_size >= self.min_fvg_size:
                    self.fvgs.append(FVGZone(
                        fvg_type=FVGType.BEARISH,
                        high=lows[i+1],
                        low=highs[i-1],
                        mid=(lows[i+1] + highs[i-1]) / 2,
                        size_pips=gap_size * 10000,
                        created_at=times[i],
                        created_index=i,
                        is_ifvg=False
                    ))

                    logger.debug(
                        f"Bearish FVG شناسایی شد | "
                        f"محدوده: {highs[i-1]:.5f} - {lows[i+1]:.5f}"
                    )

        if len(self.fvgs) > self.max_fvg_count:
            self.fvgs = self.fvgs[-self.max_fvg_count:]

    def _detect_ifvgs(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        times: List[datetime]
    ):
        """
        تشخیص IFVG (Inverse FVG)

        IFVG = FVG که تست شده و معکوس عمل می‌کند
        معمولاً بعد از تست partial یا unfilled

        الگوریتم:
        1. FVG تست شده (قیمت به mid رسیده)
        2. قیمت برگشت و FVG را پر نکرد
        3. حالا IFVG تشکیل می‌شود

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            closes: آرایه کلوزها
            times: لیست زمان‌ها
        """
        n = len(highs)

        for fvg in self.fvgs:
            if fvg.is_ifvg or fvg.status == "filled":
                continue

            # بررسی تست
            tested = False
            test_index = None

            for i in range(fvg.created_index + 1, n):
                if fvg.fvg_type == FVGType.BULLISH:
                    # تست Bullish FVG
                    if lows[i] <= fvg.mid:
                        tested = True
                        test_index = i
                        break
                else:
                    # تست Bearish FVG
                    if highs[i] >= fvg.mid:
                        tested = True
                        test_index = i
                        break

            if not tested or test_index is None:
                continue

            # بررسی برگشت (reject)
            # بعد از تست، قیمت باید برگردد
            reject_candles = min(5, n - test_index - 1)
            if reject_candles < 2:
                continue

            if fvg.fvg_type == FVGType.BULLISH:
                # برای IFVG صعودی: بعد از تست، قیمت باید بالا برود
                rejected = closes[test_index + reject_candles] > fvg.mid
                if rejected:
                    # تبدیل به IFVG
                    ifvg = FVGZone(
                        fvg_type=FVGType.IFVG,
                        high=fvg.high,
                        low=fvg.low,
                        mid=fvg.mid,
                        size_pips=fvg.size_pips,
                        created_at=times[test_index],
                        created_index=test_index,
                        status="unfilled",
                        is_ifvg=True,
                        origin_block="bullish_fvg"
                    )
                    self.ifvgs.append(ifvg)
                    logger.info(f"Bullish IFVG تشکیل شد در {fvg.mid:.5f}")

            else:  # Bearish
                rejected = closes[test_index + reject_candles] < fvg.mid
                if rejected:
                    ifvg = FVGZone(
                        fvg_type=FVGType.IFVG,
                        high=fvg.high,
                        low=fvg.low,
                        mid=fvg.mid,
                        size_pips=fvg.size_pips,
                        created_at=times[test_index],
                        created_index=test_index,
                        status="unfilled",
                        is_ifvg=True,
                        origin_block="bearish_fvg"
                    )
                    self.ifvgs.append(ifvg)
                    logger.info(f"Bearish IFVG تشکیل شد در {fvg.mid:.5f}")

    def _check_fills(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        times: List[datetime]
    ):
        """
        بررسی پر شدن FVG

        Fill levels:
        - 50%: قیمت به mid رسیده
        - 100%: قیمت به لبه opposite رسیده

        Args:
            highs: آرایه سقف‌ها
            lows: آرایه کف‌ها
            times: لیست زمان‌ها
        """
        n = len(highs)

        for fvg in self.fvgs:
            if fvg.status == "filled":
                continue

            for i in range(fvg.created_index + 1, n):
                if fvg.fvg_type == FVGType.BULLISH:
                    # Bullish FVG پر شدن از بالا
                    if lows[i] <= fvg.mid and fvg.fill_percent < 50:
                        fvg.fill_percent = 50
                        fvg.status = "partial"
                        logger.debug(f"FVG صعودی 50% پر شد")

                    if lows[i] <= fvg.low:
                        fvg.fill_percent = 100
                        fvg.status = "filled"
                        logger.debug(f"FVG صعودی کاملاً پر شد")
                        break

                elif fvg.fvg_type == FVGType.BEARISH:
                    # Bearish FVG پر شدن از پایین
                    if highs[i] >= fvg.mid and fvg.fill_percent < 50:
                        fvg.fill_percent = 50
                        fvg.status = "partial"
                        logger.debug(f"FVG نزولی 50% پر شد")

                    if highs[i] >= fvg.high:
                        fvg.fill_percent = 100
                        fvg.status = "filled"
                        logger.debug(f"FVG نزولی کاملاً پر شد")
                        break

        # بررسی IFVGها هم
        for ifvg in self.ifvgs:
            if ifvg.status == "filled":
                continue

            for i in range(ifvg.created_index + 1, n):
                if lows[i] <= ifvg.low:
                    ifvg.status = "filled"
                    ifvg.fill_percent = 100
                    break
                if highs[i] >= ifvg.high:
                    ifvg.status = "filled"
                    ifvg.fill_percent = 100
                    break

    def _calculate_score(self):
        """
        محاسبه امتیاز FVG

        عوامل:
        - FVG unfilled = امتیاز بالا
        - IFVG = امتیاز بالا
        - تعداد FVG فعال
        """
        active = self._get_active_fvgs()
        active_ifvgs = [f for f in self.ifvgs if f.status != "filled"]

        self.score = 0.0

        if active:
            for fvg in active:
                if fvg.status == "unfilled":
                    self.score = max(self.score, 8.0)
                elif fvg.status == "partial":
                    self.score = max(self.score, 5.0)

        if active_ifvgs:
            self.score += len(active_ifvgs) * 3.0

        self.score = min(self.score, 15.0)

    def _get_active_fvgs(self) -> List[FVGZone]:
        """دریافت FVGهای فعال"""
        return [f for f in self.fvgs if f.status != "filled"]

    def _fvg_to_dict(self, fvg: FVGZone) -> Dict:
        """تبدیل FVG به دیکشنری"""
        return {
            "type": fvg.fvg_type.value,
            "high": fvg.high,
            "low": fvg.low,
            "mid": fvg.mid,
            "size_pips": fvg.size_pips,
            "fill_percent": fvg.fill_percent,
            "status": fvg.status,
            "is_ifvg": fvg.is_ifvg,
            "created_at": fvg.created_at.isoformat()
        }


# =====================================================
# تحلیلگر سشن
# =====================================================

class SessionAnalyzer:
    """
    تحلیلگر سشن‌های معاملاتی

    سشن‌ها:
    - Sydney: 22:00 - 07:00 UTC
    - Tokyo: 00:00 - 09:00 UTC
    - London: 08:00 - 17:00 UTC
    - New York: 13:00 - 22:00 UTC

    Kill Zones:
    - Sydney KZ: 22:30 - 23:30 UTC
    - Tokyo KZ: 00:30 - 02:00 UTC
    - London KZ: 08:00 - 11:00 UTC
    - New York KZ: 13:30 - 16:00 UTC

    Overlaps (قدرتمندترین زمان‌ها):
    - London/NY: 13:00 - 17:00 UTC
    - Tokyo/London: 08:00 - 09:00 UTC
    """

    # زمان سشن‌ها و Kill Zone (UTC)
    SESSION_TIMES = {
        TradingSession.SYDNEY: {
            "open": 22, "close": 7,
            "kz_start": 22.5, "kz_end": 23.5
        },
        TradingSession.TOKYO: {
            "open": 0, "close": 9,
            "kz_start": 0.5, "kz_end": 2.0
        },
        TradingSession.LONDON: {
            "open": 8, "close": 17,
            "kz_start": 8.0, "kz_end": 11.0
        },
        TradingSession.NEW_YORK: {
            "open": 13, "close": 22,
            "kz_start": 13.5, "kz_end": 16.0
        }
    }

    # Overlaps مهم
    OVERLAPS = [
        {"sessions": [TradingSession.LONDON, TradingSession.NEW_YORK],
         "start": 13.0, "end": 17.0, "name": "London-NY"},
        {"sessions": [TradingSession.TOKYO, TradingSession.LONDON],
         "start": 8.0, "end": 9.0, "name": "Tokyo-London"}
    ]

    def __init__(self, config: Optional[Dict] = None):
        """مقداردهی اولیه"""
        self.config = config or {}
        logger.debug("SessionAnalyzer مقداردهی شد")

    def analyze(self, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        تحلیل سشن و Kill Zone

        Args:
            current_time: زمان فعلی (UTC)

        Returns:
            Dict شامل:
                - score: امتیاز سشن
                - active_sessions: سشن‌های فعال
                - killzone_active: آیا Kill Zone فعال است
                - active_killzones: سشن‌های در Kill Zone
                - overlaps: Overlaps فعال
                - session_strength: قدرت سشن
        """
        if current_time is None:
            current_time = datetime.utcnow()

        current_hour = current_time.hour + current_time.minute / 60

        active_sessions = []
        killzone_sessions = []
        active_overlaps = []

        # بررسی سشن‌ها
        for session, times in self.SESSION_TIMES.items():
            open_h = times["open"]
            close_h = times["close"]
            kz_start = times["kz_start"]
            kz_end = times["kz_end"]

            # بررسی باز بودن
            is_open = False
            if open_h > close_h:  # سشن شبانه
                is_open = current_hour >= open_h or current_hour < close_h
            else:
                is_open = open_h <= current_hour < close_h

            if is_open:
                active_sessions.append({
                    "session": session.value,
                    "open_hour": open_h,
                    "close_hour": close_h
                })

                # بررسی Kill Zone
                if kz_start <= current_hour < kz_end:
                    killzone_sessions.append({
                        "session": session.value,
                        "end_hour": kz_end
                    })

        # بررسی Overlaps
        for overlap in self.OVERLAPS:
            if overlap["start"] <= current_hour < overlap["end"]:
                active_overlaps.append({
                    "name": overlap["name"],
                    "end_hour": overlap["end"]
                })

        # محاسبه امتیاز
        score = 0.0
        session_strength = 0.0

        if active_overlaps:
            # Overlap = بهترین زمان
            score = 15.0
            session_strength = 100.0
        elif killzone_sessions:
            # Kill Zone = زمان خوب
            score = 10.0
            session_strength = 80.0
        elif active_sessions:
            # سشن فعال
            score = 5.0
            session_strength = 50.0
        else:
            # خارج از سشن
            score = 0.0
            session_strength = 0.0

        logger.debug(
            f"تحلیل سشن | سشن‌های فعال: {len(active_sessions)} | "
            f"Kill Zones: {len(killzone_sessions)} | امتیاز: {score}"
        )

        return {
            "score": score,
            "session_strength": session_strength,
            "active_sessions": active_sessions,
            "killzone_active": len(killzone_sessions) > 0,
            "active_killzones": killzone_sessions,
            "active_overlaps": active_overlaps,
            "current_session": (
                killzone_sessions[0]["session"] if killzone_sessions else
                (active_sessions[0]["session"] if active_sessions else None)
            ),
            "optimal_trading": len(killzone_sessions) > 0 or len(active_overlaps) > 0
        }


# =====================================================
# موتور اصلی SMC
# =====================================================



# ═══════════════════════════════════════════════════════════════════════
# Kill Zone Detector — تشخیص Kill Zone های ICT مستقیم در SMC Engine
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class KillZoneInfo:
    """اطلاعات یک Kill Zone فعال در ICT"""
    name: str
    session: str
    start_hour: int
    end_hour: int
    is_active: bool
    bias: str                   # BULLISH / BEARISH / NEUTRAL
    score_multiplier: float     # ضریب امتیاز 1.0 تا 2.0


class KillZoneDetector:
    """
    تشخیص Kill Zone های ICT داخل SMC Engine

    Kill Zone ها بهترین زمان ورود معاملاتی هستند.
    در این زمان‌ها نقدینگی جمع می‌شود و قیمت حرکت شدید می‌کند.

    - Asian Kill Zone        00:00–03:00 UTC  ضریب ۱.۳
    - London Open Kill Zone  07:00–09:00 UTC  ضریب ۱.۸
    - New York Open KZ       12:00–14:00 UTC  ضریب ۱.۹ (بهترین)
    - London Close KZ        15:00–17:00 UTC  ضریب ۱.۵
    - Power Hour KZ          19:00–20:00 UTC  ضریب ۱.۴
    """

    _ZONES: List[Dict[str, Any]] = [
        {"name": "Asian KZ",         "session": "asian",    "start": 0,  "end": 3,  "bias": "NEUTRAL", "mult": 1.3},
        {"name": "London Open KZ",   "session": "london",   "start": 7,  "end": 9,  "bias": "BULLISH", "mult": 1.8},
        {"name": "New York Open KZ", "session": "new_york", "start": 12, "end": 14, "bias": "BULLISH", "mult": 1.9},
        {"name": "London Close KZ",  "session": "london",   "start": 15, "end": 17, "bias": "BEARISH", "mult": 1.5},
        {"name": "Power Hour KZ",    "session": "new_york", "start": 19, "end": 20, "bias": "BEARISH", "mult": 1.4},
    ]

    def get_active(self, dt: datetime) -> Optional["KillZoneInfo"]:
        """Kill Zone فعال در زمان dt — None اگر خارج از Kill Zone باشیم"""
        try:
            h = dt.hour
            for z in self._ZONES:
                if z["start"] <= h < z["end"]:
                    return KillZoneInfo(
                        name=z["name"], session=z["session"],
                        start_hour=z["start"], end_hour=z["end"],
                        is_active=True, bias=z["bias"],
                        score_multiplier=z["mult"],
                    )
            return None
        except Exception as e:
            logger.error(f"خطا در KillZoneDetector.get_active: {e}")
            return None

    def is_active(self, dt: datetime) -> bool:
        """آیا الان در Kill Zone هستیم؟"""
        try:
            return self.get_active(dt) is not None
        except Exception:
            return False

    def score_bonus(self, dt: datetime) -> float:
        """بونوس امتیاز بر اساس Kill Zone فعال (0.0 تا 1.0)"""
        try:
            kz = self.get_active(dt)
            return min(kz.score_multiplier - 1.0, 1.0) if kz else 0.0
        except Exception:
            return 0.0

    def all_status(self, dt: datetime) -> List["KillZoneInfo"]:
        """وضعیت همه Kill Zone ها در زمان dt"""
        try:
            h = dt.hour
            return [
                KillZoneInfo(
                    name=z["name"], session=z["session"],
                    start_hour=z["start"], end_hour=z["end"],
                    is_active=z["start"] <= h < z["end"],
                    bias=z["bias"],
                    score_multiplier=z["mult"] if z["start"] <= h < z["end"] else 1.0,
                )
                for z in self._ZONES
            ]
        except Exception as e:
            logger.error(f"خطا در KillZoneDetector.all_status: {e}")
            return []


class SMCEngine:
    """
    موتور اصلی Smart Money Concept

    این کلاس تمام تحلیلگران را هماهنگ کرده و
    یک خروجی استاندارد برای Decision Engine تولید می‌کند.

    وزن‌دهی:
    - ساختار بازار: 35%
    - نقدینگی: 25%
    - بلاک‌ها: 25%
    - FVG: 10%
    - سشن: 5%

    خروجی:
    - SMCResult با تمام اطلاعات لازم برای تصمیم‌گیری
    """


    def _safe_execute(self, func, *args, func_name: str = "unknown", default=None, **kwargs):
        """
        اجرای امن با try/except — برای جلوگیری از crash کل موتور
        هر داده بد فقط این تابع را متوقف می‌کند نه کل سیستم
        """
        try:
            return func(*args, **kwargs)
        except (IndexError, KeyError, TypeError, ValueError) as e:
            logger.warning(f"خطای داده در {func_name}: {e}")
            return default
        except Exception as e:
            logger.error(f"خطای غیرمنتظره در {func_name}: {e}", exc_info=True)
            return default

    @staticmethod
    def _validate_candles(candles: list, min_count: int = 10) -> Tuple[bool, str]:
        """
        اعتبارسنجی کندل‌های ورودی قبل از هر تحلیل

        Returns:
            (True, "") اگر معتبر | (False, پیام خطا) اگر نامعتبر
        """
        if not candles:
            return False, "لیست کندل‌ها خالی است"
        if not isinstance(candles, (list, tuple)):
            return False, f"نوع داده نامعتبر: {type(candles)}"
        if len(candles) < min_count:
            return False, f"تعداد کندل ({len(candles)}) < حداقل ({min_count})"
        first = candles[0]
        if isinstance(first, dict):
            required = {"high", "low", "open", "close"}
            missing = required - set(first.keys())
            if missing:
                return False, f"فیلدهای گم: {missing}"
            for field_name in required:
                val = first.get(field_name)
                if val is None or not isinstance(val, (int, float)) or val <= 0:
                    return False, f"مقدار نامعتبر {field_name}: {val}"
        return True, ""

    def _safe_analyze_component(self, analyzer, candles: list, component_name: str) -> Optional[Any]:
        """
        اجرای امن یک تحلیلگر فرعی
        اگر یک تحلیلگر fail کرد، بقیه ادامه می‌دهند
        """
        try:
            result = analyzer.analyze(candles)
            return result
        except Exception as e:
            logger.error(f"خطا در {component_name}: {e}", exc_info=True)
            return None


    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات اختیاری برای هر تحلیلگر
        """
        self.config = config or {}

        # ایجاد تحلیلگران
        self.structure_analyzer = MarketStructureAnalyzer(config)
        self.liquidity_analyzer = LiquidityAnalyzer(config)
        self.block_analyzer = BlockAnalyzer(config)
        self.fvg_analyzer = FVGAnalyzer(config)
        self.session_analyzer = SessionAnalyzer(config)

        # وزن‌های پیش‌فرض
        self.weights = {
            "structure": 0.35,
            "liquidity": 0.25,
            "block": 0.25,
            "fvg": 0.10,
            "session": 0.05
        }

        logger.info(
            f"SMC Engine مقداردهی شد | "
            f"وزن‌ها: Structure={self.weights['structure']}, "
            f"Liquidity={self.weights['liquidity']}, "
            f"Blocks={self.weights['block']}"
        )

    def analyze(
        self,
        symbol: str,
        data: Dict[str, Any]
    ) -> SMCResult:
        """
        تحلیل کامل SMC

        پروسه:
        1. استخراج و بررسی داده‌ها
        2. تحلیل ساختار بازار
        3. تحلیل نقدینگی
        4. تحلیل بلاک‌ها
        5. تحلیل FVG
        6. تحلیل سشن
        7. تعیین Premium/Discount/Equilibrium
        8. محاسبه امتیاز کل

        Args:
            symbol: نماد معاملاتی
            data: دیکشنری داده‌ها شامل:
                - opens: لیست قیمت‌های باز
                - highs: لیست سقف‌ها
                - lows: لیست کف‌ها
                - closes: لیست قیمت‌های بسته
                - times: لیست زمان‌ها

        Returns:
            SMCResult: نتیجه کامل تحلیل SMC
        """
        logger.info(f"{'='*50}")
        logger.info(f"شروع تحلیل SMC برای {symbol}")

        # استخراج داده‌ها
        opens = np.array(data.get("opens", []))
        highs = np.array(data.get("highs", []))
        lows = np.array(data.get("lows", []))
        closes = np.array(data.get("closes", []))
        times = data.get("times", [])

        # تبدیل times به datetime اگر باشد
        if times and isinstance(times[0], str):
            times = [datetime.fromisoformat(t) for t in times]

        # بررسی داده کافی
        min_required = 50
        if len(highs) < min_required:
            logger.warning(f"داده کافی نیست: {len(highs)} کندل (حداقل {min_required} نیاز)")
            return self._get_empty_result()

        logger.debug(f"داده‌ها: {len(highs)} کندل دریافت شد")

        # مرحله 1: تحلیل ساختار بازار
        structure_result = self.structure_analyzer.analyze(highs, lows, closes, times)

        # مرحله 2: تحلیل نقدینگی
        liquidity_result = self.liquidity_analyzer.analyze(
            highs, lows, closes, times,
            self.structure_analyzer.swing_highs,
            self.structure_analyzer.swing_lows
        )

        # مرحله 3: تشخیص نقدینگی سشن‌ها
        session_liquidity = []
        for session in [TradingSession.TOKYO, TradingSession.LONDON, TradingSession.NEW_YORK]:
            session_liq = self.liquidity_analyzer.detect_session_liquidity(
                highs, lows, closes, times, session
            )
            session_liquidity.append(session_liq)

        # مرحله 4: تحلیل بلاک‌ها
        block_result = self.block_analyzer.analyze(
            opens, highs, lows, closes, times,
            self.structure_analyzer.structure_events
        )

        # مرحله 5: تحلیل FVG
        fvg_result = self.fvg_analyzer.analyze(highs, lows, closes, times)

        # مرحله 6: تحلیل سشن
        session_result = self.session_analyzer.analyze()

        # مرحله 7: تعیین Premium/Discount/Equilibrium
        premium_discount, equilibrium_zone = self._determine_premium_discount(
            closes[-1],
            structure_result.get("key_levels", {})
        )

        # مرحله 8: محاسبه امتیاز کل
        total_score = self._calculate_total_score(
            structure_result,
            liquidity_result,
            block_result,
            fvg_result,
            session_result
        )

        # ایجاد نتیجه نهایی
        result = SMCResult(
            total_score=total_score,
            trend=TrendDirection(structure_result["trend"]),
            trend_strength=structure_result["trend_strength"],
            last_structure_event=self.structure_analyzer.last_event,
            liquidity_swept=liquidity_result["liquidity_swept"],
            sweep_direction=liquidity_result["sweep_direction"],
            active_blocks=self.block_analyzer._get_active_blocks(),
            active_fvgs=self.fvg_analyzer._get_active_fvgs(),
            premium_discount=premium_discount,
            equilibrium_zone=equilibrium_zone,
            session_score=session_result["score"],
            killzone_active=session_result["killzone_active"],
            active_killzones=[kz["session"] for kz in session_result["active_killzones"]],
            session_liquidity=session_liquidity,
            internal_liquidity=self.liquidity_analyzer.internal_liquidity,
            details={
                "structure": structure_result,
                "liquidity": liquidity_result,
                "blocks": block_result,
                "fvg": fvg_result,
                "session": session_result
            }
        )

        logger.info(
            f"تحلیل SMC کامل شد | "
            f"روند: {result.trend.value} | "
            f"امتیاز: {result.total_score:.2f} | "
            f"سطح قیمتی: {result.premium_discount}"
        )
        logger.info(f"{'='*50}")

        return result

    def _calculate_total_score(
        self,
        structure: Dict,
        liquidity: Dict,
        blocks: Dict,
        fvg: Dict,
        session: Dict
    ) -> float:
        """
        محاسبه امتیاز کل SMC

        فرمول:
        score = Σ (component_score * weight) * 100 / max_component_score

        Args:
            structure, liquidity, blocks, fvg, session: نتایج هر تحلیل

        Returns:
            float: امتیاز کل (0-100)
        """
        max_score = 15.0  # حداکثر امتیاز هر component

        weighted_sum = (
            structure["score"] * self.weights["structure"] +
            liquidity["score"] * self.weights["liquidity"] +
            blocks["score"] * self.weights["block"] +
            fvg["score"] * self.weights["fvg"] +
            session["score"] * self.weights["session"]
        )

        # نرمال‌سازی به 0-100
        normalized = (weighted_sum / max_score) * 100

        return min(max(normalized, 0), 100)

    def _determine_premium_discount(
        self,
        current_price: float,
        levels: Dict[str, float]
    ) -> Tuple[str, Tuple[float, float]]:
        """
        تعیین ناحیه Premium/Discount/Equilibrium

        Premium: قیمت نزدیک سقف رنج (فروش بهتر)
        Discount: قیمت نزدیک کف رنج (خرید بهتر)
        Equilibrium: قیمت در میانه

        Also calculates equilibrium zone for confluence analysis.

        Args:
            current_price: قیمت فعلی
            levels: سطوح کلیدی

        Returns:
            Tuple[str, Tuple[float, float]]: (status, equilibrium_zone)
        """
        high = levels.get("range_high") or levels.get("last_swing_high")
        low = levels.get("range_low") or levels.get("last_swing_low")

        if not high or not low:
            return "equilibrium", (current_price * 0.999, current_price * 1.001)

        range_size = high - low
        equilibrium = (high + low) / 2

        # مناطق
        discount_threshold = low + range_size * 0.35
        premium_threshold = high - range_size * 0.35
        eq_low = equilibrium - range_size * 0.15
        eq_high = equilibrium + range_size * 0.15

        if current_price <= discount_threshold:
            status = "discount"
        elif current_price >= premium_threshold:
            status = "premium"
        else:
            status = "equilibrium"

        equilibrium_zone = (eq_low, eq_high)

        logger.debug(
            f"Premium/Discount | {status} | "
            f"قیمت: {current_price:.5f} | "
            f"Range: {low:.5f} - {high:.5f}"
        )

        return status, equilibrium_zone

    def _get_empty_result(self) -> SMCResult:
        """
        ایجاد نتیجه خالی برای زمانی که داده کافی نیست

        Returns:
            SMCResult: نتیجه با مقادیر پیش‌فرض
        """
        return SMCResult(
            total_score=0,
            trend=TrendDirection.NEUTRAL,
            trend_strength=0,
            last_structure_event=None,
            liquidity_swept=False,
            sweep_direction=None,
            active_blocks=[],
            active_fvgs=[],
            premium_discount="equilibrium",
            equilibrium_zone=(0, 0),
            session_score=0,
            killzone_active=False,
            active_killzones=[],
            session_liquidity=[],
            internal_liquidity=[],
            details={"error": "Insufficient data"}
        )

    def get_confluence_zones(
        self,
        result: SMCResult,
        current_price: float
    ) -> List[Dict[str, Any]]:
        """
        یافتن مناطق Confluence

        Confluence = هم‌پوشانی عوامل مختلف SMC

        عوامل:
        - بلاک فعال
        - FVG پر نشده
        - سطح نقدینگی
        - ناحیه Equilibrium

        Args:
            result: نتیجه تحلیل SMC
            current_price: قیمت فعلی

        Returns:
            List of confluence zones با امتیازدهی
        """
        confluences = []

        # بررسی هر بلاک فعال
        for block in result.active_blocks:
            zone_score = block.score

            # بررسی هم‌پوشانی با FVG
            for fvg in result.active_fvgs:
                if self._zones_overlap(block.low, block.high, fvg.low, fvg.high):
                    zone_score += 5
                    break

            # بررسی نزدیکی به Equilibrium
            eq_low, eq_high = result.equilibrium_zone
            if eq_low <= block.mid <= eq_high:
                zone_score += 3

            # بررسی نزدیکی به نقدینگی
            for liq in result.internal_liquidity:
                if abs(liq.level - block.mid) < current_price * 0.002:
                    zone_score += 3
                    break

            if zone_score >= 10:
                confluences.append({
                    "type": "block_confluence",
                    "level": block.mid,
                    "high": block.high,
                    "low": block.low,
                    "direction": block.direction.value,
                    "score": zone_score,
                    "factors": ["block", "fvg", "equilibrium", "liquidity"]
                })

        # مرتب‌سازی
        confluences.sort(key=lambda x: x["score"], reverse=True)

        return confluences[:5]  # برگرداندن 5 Confluence برتر

    def _zones_overlap(
        self,
        low1: float,
        high1: float,
        low2: float,
        high2: float
    ) -> bool:
        """
        بررسی هم‌پوشانی دو ناحیه

        Args:
            low1, high1: محدوده اول
            low2, high2: محدوده دوم

        Returns:
            bool: True اگر هم‌پوشانی داشته باشند
        """
        return not (high1 < low2 or high2 < low1)
