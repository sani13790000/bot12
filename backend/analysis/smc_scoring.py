"""
================================================================================
فایل: backend/analysis/smc_scoring.py
================================================================================
سیستم امتیازدهی کامل برای Smart Money Concept

این ماژول مسئول محاسبه امتیاز دقیق برای تمام ناحیه‌ها و سیگنال‌های SMC است.
هر ناحیه بر اساس چندین فاکتور امتیاز می‌گیرد:
- قدرت ناحیه (چند بار تست شده؟)
- همسویی با ساختار بازار (HTF/MTF/LTF)
- موقعیت در Premium/Discount Zone
- ترکیب با Kill Zone
- حجم معاملات در ناحیه
- تازگی ناحیه (Age)
- همسویی با جهت کلی بازار (Trend)

خروجی: امتیاز ۰ تا ۱۰۰ برای هر ناحیه/سیگنال
================================================================================
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
import math
import logging

logger = logging.getLogger(__name__)


class ZoneType(Enum):
    """انواع ناحیه‌های SMC"""
    ORDER_BLOCK       = "order_block"
    MITIGATION_BLOCK  = "mitigation_block"
    BREAKER_BLOCK     = "breaker_block"
    REJECTION_BLOCK   = "rejection_block"
    FVG               = "fvg"
    IFVG              = "ifvg"
    LIQUIDITY         = "liquidity"
    SESSION_LIQUIDITY = "session_liquidity"
    EQUILIBRIUM       = "equilibrium"


class MarketBias(Enum):
    """جهت کلی بازار"""
    BULLISH     = "bullish"
    BEARISH     = "bearish"
    NEUTRAL     = "neutral"
    RANGING     = "ranging"


@dataclass
class ZoneScoreInput:
    """ورودی‌های محاسبه امتیاز ناحیه SMC"""
    zone_type:          ZoneType
    direction:          str              # "bullish" یا "bearish"
    touch_count:        int = 0          # تعداد دفعات تست ناحیه
    age_candles:        int = 0          # سن ناحیه (به کندل)
    volume_ratio:       float = 1.0      # نسبت حجم به میانگین
    premium_discount:   float = 0.5      # موقعیت در PD Zone (0=discount, 1=premium)
    in_kill_zone:       bool = False      # آیا در Kill Zone است؟
    htf_aligned:        bool = False      # همسو با تایم‌فریم بالاتر؟
    mtf_aligned:        bool = False      # همسو با تایم‌فریم میانی؟
    market_bias:        MarketBias = MarketBias.NEUTRAL
    bos_confirmed:      bool = False      # BOS تأیید شده؟
    choch_confirmed:    bool = False      # CHOCH تأیید شده؟
    liquidity_swept:    bool = False      # لیکوئیدیتی sweep شده؟
    fvg_nearby:         bool = False      # FVG نزدیک وجود دارد؟
    rejection_strength: float = 0.0      # قدرت rejection (0-1)
    imbalance_size:     float = 0.0      # اندازه imbalance (پوینت)
    near_higher_tf_ob:  bool = False      # نزدیک OB تایم‌فریم بالاتر؟


@dataclass
class ZoneScore:
    """نتیجه امتیازدهی ناحیه"""
    total_score:        float = 0.0      # امتیاز کل (0-100)
    base_score:         float = 0.0      # امتیاز پایه
    structure_score:    float = 0.0      # امتیاز ساختار
    confluence_score:   float = 0.0      # امتیاز همگرایی
    timing_score:       float = 0.0      # امتیاز زمان‌بندی
    quality_grade:      str   = "F"      # درجه کیفیت: A+, A, B, C, D, F
    is_tradeable:       bool  = False    # آیا قابل معامله است؟
    min_rr_ratio:       float = 1.5      # حداقل نسبت ریسک به ریوارد
    detail:             dict  = field(default_factory=dict)


class SMCScoringEngine:
    """
    موتور امتیازدهی SMC

    این کلاس مسئول محاسبه دقیق امتیاز تمام ناحیه‌های SMC است.
    سیستم امتیازدهی چهار بُعدی:
    1. Base Score: امتیاز پایه بر اساس نوع ناحیه
    2. Structure Score: همسویی با ساختار بازار
    3. Confluence Score: همگرایی با عوامل دیگر
    4. Timing Score: زمان‌بندی (Kill Zone, Age)
    """

    # وزن‌های امتیازدهی
    WEIGHTS = {
        "base":        0.25,   # وزن امتیاز پایه
        "structure":   0.35,   # وزن ساختار (مهم‌ترین)
        "confluence":  0.25,   # وزن همگرایی
        "timing":      0.15,   # وزن زمان‌بندی
    }

    # امتیاز پایه هر نوع ناحیه
    BASE_SCORES = {
        ZoneType.ORDER_BLOCK:       85,
        ZoneType.BREAKER_BLOCK:     80,
        ZoneType.MITIGATION_BLOCK:  75,
        ZoneType.REJECTION_BLOCK:   70,
        ZoneType.FVG:               65,
        ZoneType.IFVG:              60,
        ZoneType.LIQUIDITY:         70,
        ZoneType.SESSION_LIQUIDITY: 75,
        ZoneType.EQUILIBRIUM:       55,
    }

    # آستانه‌های درجه‌بندی
    GRADE_THRESHOLDS = {
        "A+": 90, "A": 80, "B": 70, "C": 60, "D": 50
    }

    # حداقل امتیاز برای قابل معامله بودن
    MIN_TRADEABLE_SCORE = 65.0

    def __init__(self, min_score: float = 65.0):
        """
        سازنده
        min_score: حداقل امتیاز برای قابل معامله بودن
        """
        self.min_tradeable_score = min_score
        logger.info(f"SMC Scoring Engine راه‌اندازی شد | حداقل امتیاز: {min_score}")

    def calculate_zone_score(self, inp: ZoneScoreInput) -> ZoneScore:
        """
        محاسبه امتیاز کامل یک ناحیه SMC

        فرآیند محاسبه:
        1. امتیاز پایه بر اساس نوع ناحیه
        2. امتیاز ساختار (HTF/MTF alignment, BOS, CHOCH)
        3. امتیاز همگرایی (Kill Zone, Volume, FVG)
        4. امتیاز زمان‌بندی (Age, Kill Zone timing)
        5. ترکیب نهایی با وزن‌دهی
        """
        result = ZoneScore()

        # ۱. امتیاز پایه
        result.base_score = self._calculate_base_score(inp)

        # ۲. امتیاز ساختار
        result.structure_score = self._calculate_structure_score(inp)

        # ۳. امتیاز همگرایی
        result.confluence_score = self._calculate_confluence_score(inp)

        # ۴. امتیاز زمان‌بندی
        result.timing_score = self._calculate_timing_score(inp)

        # ۵. امتیاز کل وزن‌دار
        result.total_score = (
            result.base_score       * self.WEIGHTS["base"] +
            result.structure_score  * self.WEIGHTS["structure"] +
            result.confluence_score * self.WEIGHTS["confluence"] +
            result.timing_score     * self.WEIGHTS["timing"]
        )
        result.total_score = min(100.0, max(0.0, result.total_score))

        # ۶. درجه‌بندی کیفیت
        result.quality_grade = self._get_grade(result.total_score)
        result.is_tradeable  = result.total_score >= self.min_tradeable_score

        # ۷. محاسبه حداقل RR پیشنهادی
        result.min_rr_ratio = self._calculate_min_rr(inp, result.total_score)

        # ۸. جزئیات برای لاگ
        result.detail = {
            "zone_type":        inp.zone_type.value,
            "direction":        inp.direction,
            "base_score":       round(result.base_score, 2),
            "structure_score":  round(result.structure_score, 2),
            "confluence_score": round(result.confluence_score, 2),
            "timing_score":     round(result.timing_score, 2),
            "total_score":      round(result.total_score, 2),
            "grade":            result.quality_grade,
            "tradeable":        result.is_tradeable,
            "min_rr":           result.min_rr_ratio,
        }

        logger.debug(f"امتیاز ناحیه {inp.zone_type.value}: {result.total_score:.1f} ({result.quality_grade})")
        return result

    def _calculate_base_score(self, inp: ZoneScoreInput) -> float:
        """امتیاز پایه بر اساس نوع ناحیه"""
        base = float(self.BASE_SCORES.get(inp.zone_type, 50))

        # کسر برای تعداد تست زیاد (ناحیه ضعیف‌تر می‌شود)
        if inp.touch_count > 3:
            base -= (inp.touch_count - 3) * 5
        elif inp.touch_count == 0:
            base += 5  # ناحیه دست‌نخورده قوی‌تر است

        # بونوس برای rejection قوی
        if inp.rejection_strength > 0.7:
            base += inp.rejection_strength * 10

        # بونوس برای imbalance بزرگ در FVG/IFVG
        if inp.zone_type in [ZoneType.FVG, ZoneType.IFVG] and inp.imbalance_size > 0:
            base += min(10, inp.imbalance_size / 10)

        return min(100.0, max(0.0, base))

    def _calculate_structure_score(self, inp: ZoneScoreInput) -> float:
        """امتیاز ساختار بازار"""
        score = 50.0

        # همسویی HTF (بیشترین اهمیت)
        if inp.htf_aligned:
            score += 25
        else:
            score -= 20  # عدم همسویی HTF بسیار بد است

        # همسویی MTF
        if inp.mtf_aligned:
            score += 15
        else:
            score -= 10

        # BOS تأیید شده
        if inp.bos_confirmed:
            score += 15

        # CHOCH (تغییر کاراکتر - سیگنال قوی‌تر از BOS)
        if inp.choch_confirmed:
            score += 20

        # همسویی با Bias کلی بازار
        if inp.market_bias == MarketBias.BULLISH and inp.direction == "bullish":
            score += 10
        elif inp.market_bias == MarketBias.BEARISH and inp.direction == "bearish":
            score += 10
        elif inp.market_bias == MarketBias.RANGING:
            score -= 5  # رنج ریسک بیشتری دارد

        # Liquidity Sweep تأیید ورود
        if inp.liquidity_swept:
            score += 10

        # نزدیکی به OB تایم‌فریم بالاتر
        if inp.near_higher_tf_ob:
            score += 8

        return min(100.0, max(0.0, score))

    def _calculate_confluence_score(self, inp: ZoneScoreInput) -> float:
        """امتیاز همگرایی عوامل"""
        score = 40.0

        # موقعیت در Premium/Discount Zone
        # برای فروش باید premium (>0.6) و برای خرید باید discount (<0.4)
        if inp.direction == "bullish":
            if inp.premium_discount < 0.35:
                score += 25   # ناحیه discount قوی
            elif inp.premium_discount < 0.45:
                score += 15   # equilibrium قابل قبول
            else:
                score -= 20   # خرید در premium بد است

        elif inp.direction == "bearish":
            if inp.premium_discount > 0.65:
                score += 25   # ناحیه premium قوی
            elif inp.premium_discount > 0.55:
                score += 15   # equilibrium قابل قبول
            else:
                score -= 20   # فروش در discount بد است

        # حجم بالا = ناحیه معتبرتر
        if inp.volume_ratio > 2.0:
            score += 15
        elif inp.volume_ratio > 1.5:
            score += 10
        elif inp.volume_ratio < 0.8:
            score -= 10   # حجم کم ناحیه را ضعیف می‌کند

        # FVG نزدیک = confluence اضافه
        if inp.fvg_nearby:
            score += 12

        return min(100.0, max(0.0, score))

    def _calculate_timing_score(self, inp: ZoneScoreInput) -> float:
        """امتیاز زمان‌بندی"""
        score = 50.0

        # Kill Zone = بهترین زمان
        if inp.in_kill_zone:
            score += 35

        # سن ناحیه (تازه‌تر = بهتر)
        if inp.age_candles <= 5:
            score += 20   # ناحیه بسیار تازه
        elif inp.age_candles <= 15:
            score += 10
        elif inp.age_candles <= 30:
            score += 0    # قابل قبول
        elif inp.age_candles <= 60:
            score -= 10
        else:
            score -= 25   # ناحیه قدیمی ضعیف است

        return min(100.0, max(0.0, score))

    def _get_grade(self, score: float) -> str:
        """درجه‌بندی کیفیت بر اساس امتیاز"""
        if score >= 90: return "A+"
        if score >= 80: return "A"
        if score >= 70: return "B"
        if score >= 60: return "C"
        if score >= 50: return "D"
        return "F"

    def _calculate_min_rr(self, inp: ZoneScoreInput, score: float) -> float:
        """
        محاسبه حداقل نسبت ریسک به ریوارد پیشنهادی
        امتیاز بالاتر → RR پایین‌تر قابل قبول است
        """
        if score >= 85:
            return 1.5
        elif score >= 75:
            return 2.0
        elif score >= 65:
            return 2.5
        else:
            return 3.0

    def score_multiple_zones(self, zones: list[ZoneScoreInput]) -> list[tuple[ZoneScoreInput, ZoneScore]]:
        """
        امتیازدهی به چندین ناحیه و مرتب‌سازی بر اساس امتیاز

        خروجی: لیست مرتب شده از (ناحیه، امتیاز) به صورت نزولی
        """
        scored = []
        for zone in zones:
            score = self.calculate_zone_score(zone)
            scored.append((zone, score))

        # مرتب‌سازی بر اساس امتیاز کل (نزولی)
        scored.sort(key=lambda x: x[1].total_score, reverse=True)
        return scored

    def get_best_zone(self, zones: list[ZoneScoreInput]) -> Optional[tuple[ZoneScoreInput, ZoneScore]]:
        """
        بهترین ناحیه قابل معامله را برمی‌گرداند

        اگر هیچ ناحیه‌ای قابل معامله نباشد، None برمی‌گرداند
        """
        scored = self.score_multiple_zones(zones)
        for zone, score in scored:
            if score.is_tradeable:
                return zone, score
        return None
