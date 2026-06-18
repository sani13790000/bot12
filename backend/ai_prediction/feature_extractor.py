"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: FeatureExtractor

وظیفه:
  استخراج ۳۸ ویژگی عددی از سیگنال‌های SMC/PA موجود
  برای استفاده در مدل XGBoost.

ویژگی‌های استخراج‌شده:
  • SMC  (14 ویژگی): BOS, CHOCH, OB, FVG, Liquidity, Premium/Discount
  • PA   (8 ویژگی):  الگوی کندل، کیفیت، جهت، timeframe
  • بازار (8 ویژگی): ATR, Spread, Volatility, Trend
  • زمان  (8 ویژگی): Session, Hour, Day, Kill Zone
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import numpy as np

from ..core.logger import get_logger

logger = get_logger("ai_prediction.feature_extractor")


# ─── enums ────────────────────────────────────────────────────────────────────

class MarketSession(str, Enum):
    ASIAN   = "ASIAN"
    LONDON  = "LONDON"
    NEW_YORK = "NEW_YORK"
    OVERLAP  = "OVERLAP"
    OFF      = "OFF"


class TrendDirection(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH        = "BULLISH"
    NEUTRAL        = "NEUTRAL"
    BEARISH        = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


class TradeDirection(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"


# ─── input dataclass ─────────────────────────────────────────────────────────

@dataclass
class SMCSignalInput:
    """
    داده ورودی خام سیگنال SMC — از Decision Engine دریافت می‌شود.
    تمام فیلدها اختیاری هستند تا با سیگنال‌های ناقص هم کار کند.
    """
    # هویت
    symbol:              str             = "XAUUSD"
    direction:           TradeDirection  = TradeDirection.BUY
    entry_price:         float           = 0.0
    timestamp:           Optional[datetime] = None

    # SMC — ساختار بازار
    bos_detected:        bool  = False
    choch_detected:      bool  = False
    bos_strength:        float = 0.0   # 0.0 – 1.0
    choch_strength:      float = 0.0   # 0.0 – 1.0

    # SMC — Order Block
    order_block_present: bool  = False
    order_block_quality: float = 0.0   # 0.0 – 1.0
    order_block_tested:  bool  = False
    breaker_block:       bool  = False

    # SMC — FVG
    fvg_present:         bool  = False
    fvg_quality:         float = 0.0   # 0.0 – 1.0
    ifvg_present:        bool  = False

    # SMC — نقدینگی
    liquidity_sweep:     bool  = False
    liquidity_quality:   float = 0.0   # 0.0 – 1.0
    internal_liquidity:  bool  = False
    external_liquidity:  bool  = False

    # SMC — موقعیت قیمت
    in_premium_zone:     bool  = False
    in_discount_zone:    bool  = False
    equilibrium_dist:    float = 0.0   # فاصله از equilibrium (0.5 = eq)

    # Price Action
    pa_pattern:          str   = "NONE"   # نام الگو: PinBar, Engulfing, ...
    pa_quality:          float = 0.0      # 0.0 – 1.0
    pa_timeframe:        str   = "M15"

    # بازار
    atr:                 float = 0.0
    spread:              float = 0.0
    spread_ratio:        float = 0.0    # spread / ATR
    volatility_ratio:    float = 0.0    # ATR / ATR_20
    trend_direction:     TrendDirection = TrendDirection.NEUTRAL
    trend_strength:      float = 0.0    # 0.0 – 1.0
    htf_alignment:       bool  = False  # H4/D1 هم‌راستا
    htf_score:           float = 0.0    # 0.0 – 1.0

    # زمان و سشن
    session:             MarketSession = MarketSession.OFF
    in_kill_zone:        bool  = False
    hour_of_day:         int   = 0       # 0 – 23
    day_of_week:         int   = 0       # 0=Mon – 4=Fri

    # امتیاز کلی از Decision Engine
    decision_score:      float = 0.0    # 0.0 – 100.0


# ─── output dataclass ────────────────────────────────────────────────────────

@dataclass
class SMCFeatures:
    """
    ۳۸ ویژگی عددی آماده برای XGBoost.
    هر ویژگی نام و معنای دقیق دارد.
    """
    # SMC — ساختار (6 ویژگی)
    f_bos:               float = 0.0
    f_choch:             float = 0.0
    f_bos_strength:      float = 0.0
    f_choch_strength:    float = 0.0
    f_structure_score:   float = 0.0   # ترکیب BOS + CHOCH
    f_structure_count:   float = 0.0   # تعداد سیگنال‌های ساختاری

    # SMC — Order Block (4 ویژگی)
    f_ob_present:        float = 0.0
    f_ob_quality:        float = 0.0
    f_ob_tested:         float = 0.0
    f_breaker:           float = 0.0

    # SMC — FVG (3 ویژگی)
    f_fvg_present:       float = 0.0
    f_fvg_quality:       float = 0.0
    f_ifvg:              float = 0.0

    # SMC — نقدینگی (4 ویژگی)
    f_sweep:             float = 0.0
    f_sweep_quality:     float = 0.0
    f_internal_liq:      float = 0.0
    f_external_liq:      float = 0.0

    # SMC — موقعیت قیمت (3 ویژگی)
    f_in_discount:       float = 0.0
    f_in_premium:        float = 0.0
    f_eq_distance:       float = 0.0

    # Price Action (4 ویژگی)
    f_pa_quality:        float = 0.0
    f_pa_reversal:       float = 0.0   # 1 اگر الگوی برگشتی
    f_pa_continuation:   float = 0.0   # 1 اگر الگوی ادامه‌دهنده
    f_pa_strength:       float = 0.0

    # بازار (6 ویژگی)
    f_atr_normalized:    float = 0.0
    f_spread_ratio:      float = 0.0
    f_volatility_ratio:  float = 0.0
    f_trend_strength:    float = 0.0
    f_htf_aligned:       float = 0.0
    f_htf_score:         float = 0.0

    # زمان (5 ویژگی)
    f_session_quality:   float = 0.0
    f_kill_zone:         float = 0.0
    f_hour_sin:          float = 0.0   # sin(hour × 2π/24)
    f_hour_cos:          float = 0.0   # cos(hour × 2π/24)
    f_day_of_week:       float = 0.0

    # امتیاز کلی (3 ویژگی)
    f_decision_score:    float = 0.0
    f_confluence_count:  float = 0.0   # تعداد عوامل تأییدکننده
    f_confluence_ratio:  float = 0.0   # نسبت عوامل تأیید / کل عوامل

    def to_numpy(self) -> np.ndarray:
        """تبدیل به آرایه numpy برای XGBoost."""
        return np.array(list(asdict(self).values()), dtype=np.float32)

    def to_dict(self) -> Dict[str, float]:
        """تبدیل به dictionary."""
        return asdict(self)

    @classmethod
    def feature_names(cls) -> List[str]:
        """نام همه ویژگی‌ها — برای feature importance."""
        return list(cls.__dataclass_fields__.keys())


# ─── PA pattern classification ───────────────────────────────────────────────

_REVERSAL_PATTERNS = {
    "PinBar", "BullishEngulfing", "BearishEngulfing",
    "MorningStar", "EveningStar", "HammerCandle",
    "ShootingStarCandle", "BullishHarami", "BearishHarami",
}

_CONTINUATION_PATTERNS = {
    "InsideBar", "ThreeSoldiers", "ThreeCrows",
    "Breakout", "Retest", "Compression", "Expansion",
    "Fakey",
}

# امتیاز کیفی هر سشن برای معامله‌گری
_SESSION_QUALITY: Dict[MarketSession, float] = {
    MarketSession.OVERLAP:   1.00,
    MarketSession.LONDON:    0.90,
    MarketSession.NEW_YORK:  0.85,
    MarketSession.ASIAN:     0.40,
    MarketSession.OFF:       0.10,
}

# امتیاز عددی trend direction
_TREND_SCORE: Dict[TrendDirection, float] = {
    TrendDirection.STRONG_BULLISH: 1.00,
    TrendDirection.BULLISH:        0.75,
    TrendDirection.NEUTRAL:        0.50,
    TrendDirection.BEARISH:        0.25,
    TrendDirection.STRONG_BEARISH: 0.00,
}


# ─── FeatureExtractor ────────────────────────────────────────────────────────

class FeatureExtractor:
    """
    استخراج‌کننده ویژگی از سیگنال‌های SMC.

    ورودی:  SMCSignalInput  — داده خام از Decision Engine
    خروجی: SMCFeatures     — ۳۸ ویژگی عددی آماده برای ML
    """

    # تعداد کل عوامل ممکن برای محاسبه confluence_ratio
    _TOTAL_FACTORS: int = 12

    def extract(self, signal: SMCSignalInput) -> SMCFeatures:
        """
        استخراج کامل ۳۸ ویژگی از یک سیگنال.

        Args:
            signal: سیگنال SMC خام

        Returns:
            SMCFeatures: ویژگی‌های آماده برای XGBoost
        """
        try:
            return SMCFeatures(
                # SMC — ساختار
                f_bos            = float(signal.bos_detected),
                f_choch          = float(signal.choch_detected),
                f_bos_strength   = self._clamp(signal.bos_strength),
                f_choch_strength = self._clamp(signal.choch_strength),
                f_structure_score = self._calc_structure_score(signal),
                f_structure_count = self._calc_structure_count(signal),

                # SMC — Order Block
                f_ob_present = float(signal.order_block_present),
                f_ob_quality = self._clamp(signal.order_block_quality),
                f_ob_tested  = float(signal.order_block_tested),
                f_breaker    = float(signal.breaker_block),

                # SMC — FVG
                f_fvg_present = float(signal.fvg_present),
                f_fvg_quality = self._clamp(signal.fvg_quality),
                f_ifvg        = float(signal.ifvg_present),

                # SMC — نقدینگی
                f_sweep         = float(signal.liquidity_sweep),
                f_sweep_quality = self._clamp(signal.liquidity_quality),
                f_internal_liq  = float(signal.internal_liquidity),
                f_external_liq  = float(signal.external_liquidity),

                # SMC — موقعیت قیمت
                f_in_discount  = self._calc_discount_score(signal),
                f_in_premium   = self._calc_premium_score(signal),
                f_eq_distance  = self._clamp(signal.equilibrium_dist),

                # Price Action
                f_pa_quality      = self._clamp(signal.pa_quality),
                f_pa_reversal     = float(signal.pa_pattern in _REVERSAL_PATTERNS),
                f_pa_continuation = float(signal.pa_pattern in _CONTINUATION_PATTERNS),
                f_pa_strength     = self._calc_pa_strength(signal),

                # بازار
                f_atr_normalized  = self._calc_atr_norm(signal),
                f_spread_ratio    = self._clamp(signal.spread_ratio, max_val=2.0) / 2.0,
                f_volatility_ratio = self._clamp(signal.volatility_ratio, max_val=3.0) / 3.0,
                f_trend_strength  = self._clamp(signal.trend_strength),
                f_htf_aligned     = float(signal.htf_alignment),
                f_htf_score       = self._clamp(signal.htf_score),

                # زمان
                f_session_quality = _SESSION_QUALITY.get(signal.session, 0.10),
                f_kill_zone       = float(signal.in_kill_zone),
                f_hour_sin        = np.sin(signal.hour_of_day * 2 * np.pi / 24),
                f_hour_cos        = np.cos(signal.hour_of_day * 2 * np.pi / 24),
                f_day_of_week     = signal.day_of_week / 4.0,

                # امتیاز کلی
                f_decision_score    = self._clamp(signal.decision_score / 100.0),
                f_confluence_count  = self._calc_confluence_count(signal),
                f_confluence_ratio  = self._calc_confluence_ratio(signal),
            )
        except Exception as exc:
            logger.error("feature extraction failed for %s: %s", signal.symbol, exc)
            raise

    # ─── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
        return max(min_val, min(max_val, float(value)))

    def _calc_structure_score(self, s: SMCSignalInput) -> float:
        score = 0.0
        if s.bos_detected:
            score += 0.5 + s.bos_strength * 0.5
        if s.choch_detected:
            score += 0.5 + s.choch_strength * 0.5
        return self._clamp(score / 2.0 if (s.bos_detected and s.choch_detected) else score)

    def _calc_structure_count(self, s: SMCSignalInput) -> float:
        count = int(s.bos_detected) + int(s.choch_detected)
        return count / 2.0

    def _calc_discount_score(self, s: SMCSignalInput) -> float:
        """BUY در discount zone = قوی‌تر."""
        if s.direction == TradeDirection.BUY and s.in_discount_zone:
            return 1.0
        if s.direction == TradeDirection.SELL and s.in_premium_zone:
            return 1.0
        return 0.0

    def _calc_premium_score(self, s: SMCSignalInput) -> float:
        """SELL در premium zone = قوی‌تر."""
        if s.direction == TradeDirection.SELL and s.in_premium_zone:
            return 1.0
        if s.direction == TradeDirection.BUY and s.in_discount_zone:
            return 1.0
        return 0.0

    def _calc_pa_strength(self, s: SMCSignalInput) -> float:
        base = s.pa_quality
        if s.pa_pattern in _REVERSAL_PATTERNS:
            base *= 1.2
        elif s.pa_pattern in _CONTINUATION_PATTERNS:
            base *= 1.1
        return self._clamp(base)

    def _calc_atr_norm(self, s: SMCSignalInput) -> float:
        """ATR نرمال‌شده بر اساس price (0 تا 1)."""
        if s.entry_price <= 0 or s.atr <= 0:
            return 0.0
        ratio = s.atr / s.entry_price
        return self._clamp(ratio * 1000)  # × 1000 برای scale مناسب

    def _calc_confluence_count(self, s: SMCSignalInput) -> float:
        """تعداد عوامل تأییدکننده (0 تا 12) نرمال‌شده."""
        count = sum([
            s.bos_detected,
            s.choch_detected,
            s.order_block_present,
            s.fvg_present,
            s.liquidity_sweep,
            s.htf_alignment,
            s.in_kill_zone,
            s.pa_pattern not in ("NONE", ""),
            s.order_block_tested,
            s.breaker_block,
            s.internal_liquidity,
            s.external_liquidity,
        ])
        return count / self._TOTAL_FACTORS

    def _calc_confluence_ratio(self, s: SMCSignalInput) -> float:
        """نسبت عوامل با کیفیت بالا به کل."""
        quality_sum = (
            s.bos_strength * float(s.bos_detected) +
            s.choch_strength * float(s.choch_detected) +
            s.order_block_quality * float(s.order_block_present) +
            s.fvg_quality * float(s.fvg_present) +
            s.liquidity_quality * float(s.liquidity_sweep) +
            s.htf_score * float(s.htf_alignment)
        )
        active = sum([
            s.bos_detected, s.choch_detected,
            s.order_block_present, s.fvg_present,
            s.liquidity_sweep, s.htf_alignment,
        ])
        if active == 0:
            return 0.0
        return self._clamp(quality_sum / active)
