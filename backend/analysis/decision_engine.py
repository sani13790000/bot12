"""
=====================================================================
موتور تصمیم‌گیری چندمرحله‌ای - Production Ready
=====================================================================
این موتور با معماری چندمرحله‌ای (Stage-based) تصمیم معاملاتی می‌گیرد:

مرحله ۱ - فیلتر اولیه:
  - بررسی مجاز بودن نماد
  - بررسی ساعت معاملاتی و سشن‌ها
  - بررسی نوسانات (Volatility Filter)

مرحله ۲ - تحلیل Multi-Timeframe:
  - تحلیل تایم‌فریم بالا (HTF): روند کلی
  - تحلیل تایم‌فریم میانی (MTF): ساختار و ناحیه
  - تحلیل تایم‌فریم پایین (LTF): تریگر ورود

مرحله ۳ - امتیازدهی SMC:
  - Order Block، FVG، BOS، CHOCH، MSS
  - Liquidity (داخلی و خارجی)
  - Premium/Discount Zone

مرحله ۴ - امتیازدهی Price Action:
  - الگوهای شمعی
  - Breakout و Retest
  - Compression/Expansion

مرحله ۵ - فیلتر ریسک:
  - نسبت ریسک به ریوارد
  - حداکثر ضرر روزانه
  - تعداد معاملات همزمان

مرحله ۶ - تصمیم نهایی:
  - جمع امتیازات وزن‌دهی شده
  - مقایسه با حداقل امتیاز مجاز
  - خروجی: BUY / SELL / NO_TRADE

نویسنده: MT5 Trading Team
نسخه: 3.0.0
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DecisionStage(Enum):
    """مراحل تصمیم‌گیری"""
    INITIAL_FILTER = "initial_filter"
    MULTI_TIMEFRAME = "multi_timeframe"
    SMC_SCORING = "smc_scoring"
    PRICE_ACTION_SCORING = "price_action_scoring"
    RISK_FILTER = "risk_filter"
    FINAL_DECISION = "final_decision"


class TimeframeLevel(Enum):
    """سطوح تایم‌فریم"""
    HTF = "htf"   # تایم‌فریم بالا - روند کلی
    MTF = "mtf"   # تایم‌فریم میانی - ناحیه و ساختار
    LTF = "ltf"   # تایم‌فریم پایین - تریگر ورود


class TrendDirection(Enum):
    """جهت روند"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    UNKNOWN = "unknown"


@dataclass
class TimeframeAnalysis:
    """
    نتیجه تحلیل یک تایم‌فریم

    شامل روند، ساختار، ناحیه‌های کلیدی و امتیاز
    """
    timeframe: str
    level: TimeframeLevel
    trend: TrendDirection
    structure_score: float        # امتیاز ساختار بازار (0-100)
    in_key_zone: bool             # آیا در ناحیه کلیدی است؟
    zone_type: str                # نوع ناحیه (OB, FVG, ...)
    zone_score: float             # امتیاز کیفیت ناحیه (0-100)
    momentum_score: float         # امتیاز مومنتوم (0-100)
    aligned_with_htf: bool        # همسو با تایم‌فریم بالا
    confluence_count: int         # تعداد عوامل همگرا
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SMCScoreResult:
    """
    نتیجه امتیازدهی Smart Money Concept

    هر مفهوم SMC امتیاز جداگانه دارد و در نهایت وزن‌دهی می‌شود.
    """
    # ساختار بازار
    market_structure_score: float = 0.0    # BOS، CHOCH، MSS
    bos_confirmed: bool = False
    choch_confirmed: bool = False
    mss_confirmed: bool = False

    # ناحیه‌های معاملاتی
    order_block_score: float = 0.0         # Order Block کیفیت
    mitigation_block_score: float = 0.0   # Mitigation Block
    breaker_block_score: float = 0.0      # Breaker Block
    rejection_block_score: float = 0.0    # Rejection Block

    # شکاف‌های قیمتی
    fvg_score: float = 0.0                # Fair Value Gap
    ifvg_score: float = 0.0              # Inverse FVG

    # نقدینگی
    internal_liquidity_score: float = 0.0
    external_liquidity_score: float = 0.0
    liquidity_sweep_confirmed: bool = False

    # ناحیه قیمتی
    premium_discount_score: float = 0.0   # آیا در discount/premium است؟
    equilibrium_score: float = 0.0        # فاصله از تعادل

    # سشن
    kill_zone_active: bool = False
    session_liquidity_score: float = 0.0

    # امتیاز کلی SMC
    total_score: float = 0.0
    confidence: float = 0.0


@dataclass
class PAScoreResult:
    """
    نتیجه امتیازدهی Price Action

    هر الگو امتیاز جداگانه دارد بر اساس کیفیت و موقعیت آن.
    """
    # الگوهای شمعی تک شمعی
    pin_bar_score: float = 0.0
    doji_score: float = 0.0

    # الگوهای دو شمعی
    engulfing_score: float = 0.0
    inside_bar_score: float = 0.0
    outside_bar_score: float = 0.0

    # الگوهای پیچیده
    fakey_score: float = 0.0
    morning_star_score: float = 0.0
    evening_star_score: float = 0.0
    three_soldiers_score: float = 0.0
    three_crows_score: float = 0.0

    # الگوهای ساختاری
    breakout_score: float = 0.0
    retest_score: float = 0.0
    compression_score: float = 0.0
    expansion_score: float = 0.0

    # جهت سیگنال از PA
    bullish_signals: int = 0
    bearish_signals: int = 0

    # امتیاز کلی PA
    total_score: float = 0.0
    dominant_direction: str = "neutral"


@dataclass
class MultiTimeframeResult:
    """
    نتیجه تحلیل Multi-Timeframe

    تحلیل سه سطح تایم‌فریم و همسویی بین آن‌ها
    """
    htf: TimeframeAnalysis          # تایم‌فریم بالا
    mtf: TimeframeAnalysis          # تایم‌فریم میانی
    ltf: TimeframeAnalysis          # تایم‌فریم پایین

    # همسویی
    all_aligned: bool = False        # هر سه همسو هستند؟
    htf_mtf_aligned: bool = False   # HTF و MTF همسو
    mtf_ltf_aligned: bool = False   # MTF و LTF همسو

    # جهت کلی
    overall_direction: TrendDirection = TrendDirection.UNKNOWN

    # امتیاز همسویی (0-100)
    alignment_score: float = 0.0

    # امتیاز کلی MTF
    total_score: float = 0.0


@dataclass
class RiskAssessment:
    """
    ارزیابی ریسک معامله

    تمام پارامترهای ریسک بررسی می‌شود.
    """
    # نسبت‌ها
    risk_reward_ratio: float = 0.0     # نسبت ریسک به ریوارد
    risk_percent: float = 0.0          # درصد ریسک از موجودی

    # فیلترها
    rr_pass: bool = False              # RR حداقل 1:1.5 باشد
    daily_loss_pass: bool = False      # حداکثر ضرر روزانه رد نشده
    max_trades_pass: bool = False      # تعداد معاملات همزمان مجاز
    volatility_pass: bool = False      # نوسانات در محدوده مجاز
    spread_pass: bool = False          # اسپرد در حد مجاز

    # امتیاز ریسک (هر چه بالاتر بهتر)
    risk_score: float = 0.0

    # دلایل رد
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class DecisionResult:
    """
    نتیجه نهایی موتور تصمیم‌گیری

    شامل تصمیم، امتیاز کامل، و تمام جزئیات برای لاگ و داشبورد
    """
    # تصمیم اصلی
    decision: str = "NO_TRADE"         # BUY / SELL / NO_TRADE

    # امتیازات هر مرحله
    mtf_score: float = 0.0
    smc_score: float = 0.0
    pa_score: float = 0.0
    risk_score: float = 0.0
    session_score: float = 0.0

    # امتیاز کلی نهایی
    total_score: float = 0.0
    minimum_required_score: float = 65.0

    # اطلاعات ورود
    suggested_direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0

    # جزئیات تحلیل
    mtf_result: Optional[MultiTimeframeResult] = None
    smc_result: Optional[SMCScoreResult] = None
    pa_result: Optional[PAScoreResult] = None
    risk_assessment: Optional[RiskAssessment] = None

    # لاگ
    stage_log: List[str] = field(default_factory=list)
    rejection_reason: str = ""
    confluence_factors: List[str] = field(default_factory=list)

    # متادیتا
    symbol: str = ""
    timeframe: str = ""
    analysis_time: str = ""


# وزن‌های هر بخش در امتیاز نهایی
SCORE_WEIGHTS = {
    "mtf_alignment": 0.25,     # همسویی Multi-Timeframe
    "smc": 0.35,               # Smart Money Concept
    "price_action": 0.20,      # Price Action
    "risk_quality": 0.10,      # کیفیت ریسک
    "session": 0.10,           # سشن و Kill Zone
}

# حداقل امتیاز هر مرحله برای ادامه
STAGE_MINIMUM_SCORES = {
    DecisionStage.MULTI_TIMEFRAME: 40.0,
    DecisionStage.SMC_SCORING: 45.0,
    DecisionStage.PRICE_ACTION_SCORING: 30.0,
    DecisionStage.RISK_FILTER: 50.0,
}

# حداقل امتیاز نهایی برای ورود به معامله
MINIMUM_ENTRY_SCORE = 65.0


class MultiTimeframeEngine:
    """
    موتور تحلیل Multi-Timeframe

    تحلیل سه سطح تایم‌فریم و محاسبه امتیاز همسویی
    """

    # نگاشت تایم‌فریم‌ها به سطوح
    TIMEFRAME_LEVELS = {
        "M1": {"htf": "H1", "mtf": "M15", "ltf": "M1"},
        "M5": {"htf": "H4", "mtf": "H1", "ltf": "M5"},
        "M15": {"htf": "H4", "mtf": "H1", "ltf": "M15"},
        "M30": {"htf": "D1", "mtf": "H4", "ltf": "M30"},
        "H1": {"htf": "W1", "mtf": "D1", "ltf": "H1"},
        "H4": {"htf": "W1", "mtf": "D1", "ltf": "H4"},
        "D1": {"htf": "MN1", "mtf": "W1", "ltf": "D1"},
    }

    def analyze(
        self,
        symbol: str,
        base_timeframe: str,
        smc_engine_results: Dict[str, Any],
        pa_engine_results: Dict[str, Any]
    ) -> MultiTimeframeResult:
        """
        تحلیل کامل Multi-Timeframe

        پارامترها:
            symbol: نماد معاملاتی
            base_timeframe: تایم‌فریم پایه تحلیل
            smc_engine_results: نتایج SMC برای هر تایم‌فریم
            pa_engine_results: نتایج PA برای هر تایم‌فریم
        """
        levels = self.TIMEFRAME_LEVELS.get(base_timeframe, self.TIMEFRAME_LEVELS["H1"])

        htf_tf = levels["htf"]
        mtf_tf = levels["mtf"]
        ltf_tf = levels["ltf"]

        # تحلیل هر سطح
        htf_analysis = self._analyze_timeframe(
            htf_tf, TimeframeLevel.HTF,
            smc_engine_results.get(htf_tf, {}),
            pa_engine_results.get(htf_tf, {})
        )

        mtf_analysis = self._analyze_timeframe(
            mtf_tf, TimeframeLevel.MTF,
            smc_engine_results.get(mtf_tf, {}),
            pa_engine_results.get(mtf_tf, {}),
            reference_trend=htf_analysis.trend
        )

        ltf_analysis = self._analyze_timeframe(
            ltf_tf, TimeframeLevel.LTF,
            smc_engine_results.get(ltf_tf, {}),
            pa_engine_results.get(ltf_tf, {}),
            reference_trend=mtf_analysis.trend
        )

        # محاسبه همسویی
        htf_mtf_aligned = self._are_trends_aligned(htf_analysis.trend, mtf_analysis.trend)
        mtf_ltf_aligned = self._are_trends_aligned(mtf_analysis.trend, ltf_analysis.trend)
        all_aligned = htf_mtf_aligned and mtf_ltf_aligned

        # تعیین جهت کلی
        overall_direction = self._determine_overall_direction(
            htf_analysis.trend, mtf_analysis.trend, ltf_analysis.trend
        )

        # محاسبه امتیاز همسویی
        alignment_score = self._calculate_alignment_score(
            htf_analysis, mtf_analysis, ltf_analysis,
            htf_mtf_aligned, mtf_ltf_aligned, all_aligned
        )

        # امتیاز کلی MTF
        total_score = (
            htf_analysis.structure_score * 0.30 +
            mtf_analysis.structure_score * 0.35 +
            ltf_analysis.structure_score * 0.15 +
            alignment_score * 0.20
        )

        return MultiTimeframeResult(
            htf=htf_analysis,
            mtf=mtf_analysis,
            ltf=ltf_analysis,
            htf_mtf_aligned=htf_mtf_aligned,
            mtf_ltf_aligned=mtf_ltf_aligned,
            all_aligned=all_aligned,
            overall_direction=overall_direction,
            alignment_score=alignment_score,
            total_score=min(100.0, total_score)
        )

    def _analyze_timeframe(
        self,
        timeframe: str,
        level: TimeframeLevel,
        smc_data: Dict[str, Any],
        pa_data: Dict[str, Any],
        reference_trend: Optional[TrendDirection] = None
    ) -> TimeframeAnalysis:
        """
        تحلیل یک تایم‌فریم خاص

        پارامترها:
            timeframe: نام تایم‌فریم
            level: سطح (HTF/MTF/LTF)
            smc_data: داده‌های SMC
            pa_data: داده‌های PA
            reference_trend: روند تایم‌فریم بالاتر
        """
        # استخراج روند از داده‌های SMC
        trend = self._extract_trend(smc_data)

        # محاسبه امتیاز ساختار
        structure_score = self._calculate_structure_score(smc_data)

        # بررسی ناحیه کلیدی
        in_key_zone, zone_type, zone_score = self._check_key_zone(smc_data)

        # محاسبه مومنتوم
        momentum_score = self._calculate_momentum(pa_data)

        # بررسی همسویی با تایم‌فریم بالا
        aligned = self._are_trends_aligned(trend, reference_trend) if reference_trend else True

        # شمارش عوامل همگرا
        confluence_count = self._count_confluence_factors(smc_data, pa_data, in_key_zone, aligned)

        return TimeframeAnalysis(
            timeframe=timeframe,
            level=level,
            trend=trend,
            structure_score=structure_score,
            in_key_zone=in_key_zone,
            zone_type=zone_type,
            zone_score=zone_score,
            momentum_score=momentum_score,
            aligned_with_htf=aligned,
            confluence_count=confluence_count,
            raw_data={"smc": smc_data, "pa": pa_data}
        )

    def _extract_trend(self, smc_data: Dict[str, Any]) -> TrendDirection:
        """استخراج جهت روند از داده‌های SMC"""
        market_structure = smc_data.get("market_structure", {})

        bullish_bos = market_structure.get("bullish_bos_count", 0)
        bearish_bos = market_structure.get("bearish_bos_count", 0)
        last_bos = market_structure.get("last_bos_direction", "")

        if last_bos == "bullish" and bullish_bos > bearish_bos:
            return TrendDirection.BULLISH
        elif last_bos == "bearish" and bearish_bos > bullish_bos:
            return TrendDirection.BEARISH
        elif abs(bullish_bos - bearish_bos) <= 1:
            return TrendDirection.RANGING
        else:
            return TrendDirection.UNKNOWN

    def _calculate_structure_score(self, smc_data: Dict[str, Any]) -> float:
        """محاسبه امتیاز ساختار بازار"""
        score = 0.0

        ms = smc_data.get("market_structure", {})
        if ms.get("has_clear_trend"):
            score += 30.0
        if ms.get("bos_confirmed"):
            score += 25.0
        if ms.get("choch_detected"):
            score += 20.0
        if ms.get("higher_highs_confirmed") or ms.get("lower_lows_confirmed"):
            score += 15.0
        if ms.get("structure_clean"):
            score += 10.0

        return min(100.0, score)

    def _check_key_zone(self, smc_data: Dict[str, Any]) -> Tuple[bool, str, float]:
        """
        بررسی حضور در ناحیه کلیدی

        برمی‌گرداند: (در ناحیه است، نوع ناحیه، امتیاز ناحیه)
        """
        zones = {
            "order_block": (smc_data.get("order_blocks", []), 40.0),
            "fvg": (smc_data.get("fvg_zones", []), 30.0),
            "mitigation_block": (smc_data.get("mitigation_blocks", []), 35.0),
            "breaker_block": (smc_data.get("breaker_blocks", []), 38.0),
        }

        best_zone = ""
        best_score = 0.0

        for zone_type, (zone_list, base_score) in zones.items():
            for zone in zone_list:
                if zone.get("price_in_zone") and zone.get("score", 0) > best_score:
                    best_score = zone.get("score", base_score)
                    best_zone = zone_type

        return best_score > 0, best_zone, best_score

    def _calculate_momentum(self, pa_data: Dict[str, Any]) -> float:
        """محاسبه امتیاز مومنتوم از داده‌های PA"""
        score = 0.0

        if pa_data.get("expansion_detected"):
            score += 35.0
        if pa_data.get("compression_detected"):
            score += 20.0
        if pa_data.get("strong_candle_pattern"):
            score += 25.0
        if pa_data.get("volume_confirmation"):
            score += 20.0

        return min(100.0, score)

    def _are_trends_aligned(self, trend1: TrendDirection, trend2: Optional[TrendDirection]) -> bool:
        """بررسی همسویی دو روند"""
        if trend2 is None:
            return True
        if trend1 == TrendDirection.RANGING or trend2 == TrendDirection.RANGING:
            return False
        if trend1 == TrendDirection.UNKNOWN or trend2 == TrendDirection.UNKNOWN:
            return False
        return trend1 == trend2

    def _determine_overall_direction(
        self,
        htf: TrendDirection,
        mtf: TrendDirection,
        ltf: TrendDirection
    ) -> TrendDirection:
        """تعیین جهت کلی بازار از سه تایم‌فریم"""
        directions = [htf, mtf, ltf]
        bullish_count = directions.count(TrendDirection.BULLISH)
        bearish_count = directions.count(TrendDirection.BEARISH)

        if bullish_count >= 2:
            return TrendDirection.BULLISH
        elif bearish_count >= 2:
            return TrendDirection.BEARISH
        else:
            return TrendDirection.RANGING

    def _calculate_alignment_score(
        self,
        htf: TimeframeAnalysis,
        mtf: TimeframeAnalysis,
        ltf: TimeframeAnalysis,
        htf_mtf_aligned: bool,
        mtf_ltf_aligned: bool,
        all_aligned: bool
    ) -> float:
        """محاسبه امتیاز کیفیت همسویی"""
        score = 0.0

        if all_aligned:
            score += 50.0
        elif htf_mtf_aligned:
            score += 30.0
        elif mtf_ltf_aligned:
            score += 20.0

        # بونوس برای ناحیه کلیدی در MTF
        if mtf.in_key_zone:
            score += 25.0

        # بونوس برای کنفلوئنس بالا
        total_confluence = htf.confluence_count + mtf.confluence_count + ltf.confluence_count
        score += min(25.0, total_confluence * 5.0)

        return min(100.0, score)

    def _count_confluence_factors(
        self,
        smc_data: Dict[str, Any],
        pa_data: Dict[str, Any],
        in_key_zone: bool,
        aligned_with_higher: bool
    ) -> int:
        """شمارش عوامل همگرا"""
        count = 0

        if in_key_zone:
            count += 1
        if aligned_with_higher:
            count += 1
        if smc_data.get("market_structure", {}).get("bos_confirmed"):
            count += 1
        if smc_data.get("liquidity_sweep_detected"):
            count += 1
        if pa_data.get("pattern_detected"):
            count += 1
        if smc_data.get("kill_zone_active"):
            count += 1

        return count


class DecisionEngine:
    """
    موتور اصلی تصمیم‌گیری - Stage-Based

    این کلاس تمام مراحل تحلیل را اجرا کرده و تصمیم نهایی را می‌گیرد.
    هر مرحله می‌تواند فرآیند را متوقف کند اگر امتیاز کافی نباشد.
    """

    def __init__(
        self,
        minimum_entry_score: float = MINIMUM_ENTRY_SCORE,
        enabled_modules: Optional[Dict[str, bool]] = None
    ):
        """
        مقداردهی اولیه موتور تصمیم‌گیری

        پارامترها:
            minimum_entry_score: حداقل امتیاز برای ورود به معامله
            enabled_modules: ماژول‌های فعال (امکان غیرفعال کردن)
        """
        self.minimum_entry_score = minimum_entry_score
        self.mtf_engine = MultiTimeframeEngine()

        # ماژول‌های فعال - همه به صورت پیشفرض فعال
        self.enabled_modules = enabled_modules or {
            "multi_timeframe": True,
            "smc": True,
            "price_action": True,
            "risk_filter": True,
            "session_filter": True,
        }

        logger.info(
            f"موتور تصمیم‌گیری آماده - حداقل امتیاز: {minimum_entry_score}"
        )

    def decide(
        self,
        symbol: str,
        timeframe: str,
        smc_results: Dict[str, Any],
        pa_results: Dict[str, Any],
        market_context: Dict[str, Any]
    ) -> DecisionResult:
        """
        اجرای کامل فرآیند تصمیم‌گیری چندمرحله‌ای

        پارامترها:
            symbol: نماد معاملاتی
            timeframe: تایم‌فریم پایه
            smc_results: نتایج کامل موتور SMC
            pa_results: نتایج کامل موتور PA
            market_context: اطلاعات بازار (موجودی، معاملات باز، ...)
        """
        result = DecisionResult(
            symbol=symbol,
            timeframe=timeframe,
            analysis_time=datetime.now(timezone.utc).isoformat(),
            minimum_required_score=self.minimum_entry_score
        )

        logger.info(f"[{symbol}][{timeframe}] شروع فرآیند تصمیم‌گیری")

        # ===== مرحله ۱: فیلتر اولیه =====
        passed, reason = self._stage_initial_filter(symbol, timeframe, market_context, result)
        if not passed:
            result.decision = "NO_TRADE"
            result.rejection_reason = reason
            logger.info(f"[{symbol}] رد در مرحله فیلتر اولیه: {reason}")
            return result

        # ===== مرحله ۲: تحلیل Multi-Timeframe =====
        if self.enabled_modules.get("multi_timeframe", True):
            mtf_result = self._stage_multi_timeframe(symbol, timeframe, smc_results, pa_results, result)
            result.mtf_result = mtf_result
            result.mtf_score = mtf_result.total_score

            if result.mtf_score < STAGE_MINIMUM_SCORES[DecisionStage.MULTI_TIMEFRAME]:
                result.decision = "NO_TRADE"
                result.rejection_reason = f"امتیاز MTF ناکافی: {result.mtf_score:.1f}"
                return result

        # ===== مرحله ۳: امتیازدهی SMC =====
        if self.enabled_modules.get("smc", True):
            smc_score_result = self._stage_smc_scoring(smc_results.get(timeframe, {}), result)
            result.smc_result = smc_score_result
            result.smc_score = smc_score_result.total_score

            if result.smc_score < STAGE_MINIMUM_SCORES[DecisionStage.SMC_SCORING]:
                result.decision = "NO_TRADE"
                result.rejection_reason = f"امتیاز SMC ناکافی: {result.smc_score:.1f}"
                return result

        # ===== مرحله ۴: امتیازدهی Price Action =====
        if self.enabled_modules.get("price_action", True):
            pa_score_result = self._stage_pa_scoring(pa_results.get(timeframe, {}), result)
            result.pa_result = pa_score_result
            result.pa_score = pa_score_result.total_score

        # ===== مرحله ۵: فیلتر ریسک =====
        if self.enabled_modules.get("risk_filter", True):
            risk_assessment = self._stage_risk_filter(symbol, market_context, result)
            result.risk_assessment = risk_assessment
            result.risk_score = risk_assessment.risk_score

            if not risk_assessment.rr_pass or not risk_assessment.daily_loss_pass:
                result.decision = "NO_TRADE"
                result.rejection_reason = f"فیلتر ریسک: {', '.join(risk_assessment.rejection_reasons)}"
                return result

        # ===== مرحله ۶: تصمیم نهایی =====
        self._stage_final_decision(result)

        logger.info(
            f"[{symbol}][{timeframe}] تصمیم: {result.decision} | "
            f"امتیاز: {result.total_score:.1f}"
        )

        return result

    def _stage_initial_filter(
        self,
        symbol: str,
        timeframe: str,
        context: Dict[str, Any],
        result: DecisionResult
    ) -> Tuple[bool, str]:
        """
        مرحله ۱: فیلتر اولیه

        بررسی‌های پایه قبل از شروع تحلیل اصلی
        """
        result.stage_log.append(f"✅ مرحله ۱: فیلتر اولیه شروع شد")

        # بررسی فعال بودن ربات
        if not context.get("bot_running", True):
            return False, "ربات در حالت متوقف است"

        # بررسی مجاز بودن نماد
        allowed_symbols = context.get("allowed_symbols", [])
        if allowed_symbols and symbol not in allowed_symbols:
            return False, f"نماد {symbol} مجاز نیست"

        # بررسی ساعت معاملاتی
        if not context.get("trading_hours_active", True):
            return False, "خارج از ساعت معاملاتی"

        # بررسی نوسانات بازار
        current_spread = context.get("current_spread", 0)
        max_spread = context.get("max_allowed_spread", 30)
        if current_spread > max_spread:
            return False, f"اسپرد بالا: {current_spread} > {max_spread}"

        result.stage_log.append("✅ فیلتر اولیه پاس شد")
        return True, ""

    def _stage_multi_timeframe(
        self,
        symbol: str,
        timeframe: str,
        smc_results: Dict[str, Any],
        pa_results: Dict[str, Any],
        result: DecisionResult
    ) -> MultiTimeframeResult:
        """مرحله ۲: تحلیل Multi-Timeframe"""
        result.stage_log.append("🔍 مرحله ۲: تحلیل Multi-Timeframe")

        mtf_result = self.mtf_engine.analyze(symbol, timeframe, smc_results, pa_results)

        result.stage_log.append(
            f"  HTF: {mtf_result.htf.trend.value} | "
            f"MTF: {mtf_result.mtf.trend.value} | "
            f"LTF: {mtf_result.ltf.trend.value} | "
            f"همسو: {'بله' if mtf_result.all_aligned else 'خیر'} | "
            f"امتیاز: {mtf_result.total_score:.1f}"
        )

        return mtf_result

    def _stage_smc_scoring(
        self,
        smc_data: Dict[str, Any],
        result: DecisionResult
    ) -> SMCScoreResult:
        """
        مرحله ۳: امتیازدهی کامل SMC

        هر مفهوم SMC امتیاز جداگانه دریافت می‌کند
        """
        result.stage_log.append("🧠 مرحله ۳: امتیازدهی SMC")

        smc = SMCScoreResult()

        # ====== ساختار بازار ======
        ms = smc_data.get("market_structure", {})

        # BOS - شکست ساختار
        if ms.get("bos_confirmed"):
            smc.bos_confirmed = True
            bos_quality = ms.get("bos_quality", 0.5)
            smc.market_structure_score += 25.0 * bos_quality
            result.confluence_factors.append("BOS تأیید شد")

        # CHOCH - تغییر کاراکتر
        if ms.get("choch_detected"):
            smc.choch_confirmed = True
            choch_quality = ms.get("choch_quality", 0.5)
            smc.market_structure_score += 20.0 * choch_quality
            result.confluence_factors.append("CHOCH شناسایی شد")

        # MSS - شکست ساختار اصلی
        if ms.get("mss_detected"):
            smc.mss_confirmed = True
            smc.market_structure_score += 15.0

        smc.market_structure_score = min(100.0, smc.market_structure_score)

        # ====== Order Block ======
        obs = smc_data.get("order_blocks", [])
        best_ob = max(obs, key=lambda x: x.get("score", 0), default=None) if obs else None
        if best_ob and best_ob.get("price_in_zone"):
            smc.order_block_score = min(100.0, best_ob.get("score", 0) * 100)
            result.confluence_factors.append(f"Order Block فعال ({smc.order_block_score:.0f})")

        # ====== FVG ======
        fvgs = smc_data.get("fvg_zones", [])
        best_fvg = max(fvgs, key=lambda x: x.get("score", 0), default=None) if fvgs else None
        if best_fvg and best_fvg.get("price_in_zone"):
            smc.fvg_score = min(100.0, best_fvg.get("score", 0) * 100)
            result.confluence_factors.append(f"FVG فعال ({smc.fvg_score:.0f})")

        # ====== Liquidity ======
        liq = smc_data.get("liquidity", {})
        if liq.get("sweep_detected"):
            smc.liquidity_sweep_confirmed = True
            smc.external_liquidity_score = min(100.0, liq.get("sweep_quality", 0.5) * 100)
            result.confluence_factors.append("Liquidity Sweep تأیید شد")

        smc.internal_liquidity_score = min(100.0, liq.get("internal_liq_score", 0) * 100)

        # ====== Premium/Discount ======
        pd_zone = smc_data.get("premium_discount", {})
        if pd_zone.get("in_discount_for_buy") or pd_zone.get("in_premium_for_sell"):
            smc.premium_discount_score = min(100.0, pd_zone.get("quality_score", 0.5) * 100)
            result.confluence_factors.append("در ناحیه Premium/Discount مناسب")

        # ====== Kill Zone ======
        if smc_data.get("kill_zone_active"):
            smc.kill_zone_active = True
            smc.session_liquidity_score = 80.0
            result.confluence_factors.append("Kill Zone فعال")

        # محاسبه امتیاز کلی SMC با وزن‌دهی
        smc.total_score = (
            smc.market_structure_score * 0.30 +
            smc.order_block_score * 0.20 +
            smc.fvg_score * 0.15 +
            smc.external_liquidity_score * 0.15 +
            smc.premium_discount_score * 0.10 +
            smc.session_liquidity_score * 0.10
        )

        smc.confidence = min(1.0, len(result.confluence_factors) / 6.0)

        result.stage_log.append(f"  SMC امتیاز: {smc.total_score:.1f} | کنفلوئنس: {len(result.confluence_factors)}")

        return smc

    def _stage_pa_scoring(
        self,
        pa_data: Dict[str, Any],
        result: DecisionResult
    ) -> PAScoreResult:
        """
        مرحله ۴: امتیازدهی Price Action

        هر الگوی شمعی امتیاز بر اساس کیفیت و موقعیت دریافت می‌کند
        """
        result.stage_log.append("📈 مرحله ۴: امتیازدهی Price Action")

        pa = PAScoreResult()

        patterns = pa_data.get("detected_patterns", {})

        # ====== الگوهای صعودی ======
        if patterns.get("bullish_pin_bar"):
            pa.pin_bar_score = min(100.0, patterns["bullish_pin_bar"].get("quality", 0.5) * 100)
            pa.bullish_signals += 1

        if patterns.get("bullish_engulfing"):
            pa.engulfing_score = min(100.0, patterns["bullish_engulfing"].get("quality", 0.5) * 100)
            pa.bullish_signals += 1

        if patterns.get("morning_star"):
            pa.morning_star_score = min(100.0, patterns["morning_star"].get("quality", 0.5) * 100)
            pa.bullish_signals += 2

        if patterns.get("three_white_soldiers"):
            pa.three_soldiers_score = min(100.0, patterns["three_white_soldiers"].get("quality", 0.5) * 100)
            pa.bullish_signals += 2

        # ====== الگوهای نزولی ======
        if patterns.get("bearish_pin_bar"):
            pa.pin_bar_score = min(100.0, patterns["bearish_pin_bar"].get("quality", 0.5) * 100)
            pa.bearish_signals += 1

        if patterns.get("bearish_engulfing"):
            pa.engulfing_score = min(100.0, patterns["bearish_engulfing"].get("quality", 0.5) * 100)
            pa.bearish_signals += 1

        if patterns.get("evening_star"):
            pa.evening_star_score = min(100.0, patterns["evening_star"].get("quality", 0.5) * 100)
            pa.bearish_signals += 2

        if patterns.get("three_black_crows"):
            pa.three_crows_score = min(100.0, patterns["three_black_crows"].get("quality", 0.5) * 100)
            pa.bearish_signals += 2

        # ====== الگوهای ساختاری ======
        if patterns.get("inside_bar"):
            pa.inside_bar_score = min(100.0, patterns["inside_bar"].get("quality", 0.5) * 100)

        if patterns.get("fakey"):
            pa.fakey_score = min(100.0, patterns["fakey"].get("quality", 0.5) * 100)
            if patterns["fakey"].get("direction") == "bullish":
                pa.bullish_signals += 1
            else:
                pa.bearish_signals += 1

        if pa_data.get("breakout_detected"):
            pa.breakout_score = min(100.0, pa_data.get("breakout_quality", 0.5) * 100)

        if pa_data.get("retest_confirmed"):
            pa.retest_score = min(100.0, pa_data.get("retest_quality", 0.5) * 100)
            result.confluence_factors.append("Retest تأیید شد")

        if pa_data.get("compression_detected"):
            pa.compression_score = 70.0
            result.confluence_factors.append("Compression شناسایی شد")

        if pa_data.get("expansion_detected"):
            pa.expansion_score = min(100.0, pa_data.get("expansion_quality", 0.5) * 100)

        # تعیین جهت غالب
        if pa.bullish_signals > pa.bearish_signals:
            pa.dominant_direction = "bullish"
        elif pa.bearish_signals > pa.bullish_signals:
            pa.dominant_direction = "bearish"
        else:
            pa.dominant_direction = "neutral"

        # محاسبه امتیاز کلی
        all_scores = [
            pa.pin_bar_score, pa.engulfing_score, pa.fakey_score,
            pa.inside_bar_score, pa.morning_star_score, pa.evening_star_score,
            pa.three_soldiers_score, pa.three_crows_score,
            pa.breakout_score, pa.retest_score
        ]

        nonzero_scores = [s for s in all_scores if s > 0]
        pa.total_score = sum(nonzero_scores) / len(nonzero_scores) if nonzero_scores else 0.0

        # بونوس برای چند الگوی همزمان
        if len(nonzero_scores) >= 2:
            pa.total_score = min(100.0, pa.total_score * 1.15)

        result.stage_log.append(
            f"  PA امتیاز: {pa.total_score:.1f} | "
            f"صعودی: {pa.bullish_signals} | نزولی: {pa.bearish_signals}"
        )

        return pa

    def _stage_risk_filter(
        self,
        symbol: str,
        context: Dict[str, Any],
        result: DecisionResult
    ) -> RiskAssessment:
        """
        مرحله ۵: فیلتر ریسک

        تمام پارامترهای ریسک ارزیابی می‌شود
        """
        result.stage_log.append("⚖️ مرحله ۵: فیلتر ریسک")

        risk = RiskAssessment()

        # نسبت ریسک به ریوارد
        risk.risk_reward_ratio = context.get("risk_reward_ratio", 0.0)
        min_rr = context.get("min_risk_reward", 1.5)
        risk.rr_pass = risk.risk_reward_ratio >= min_rr
        if not risk.rr_pass:
            risk.rejection_reasons.append(f"RR ناکافی: {risk.risk_reward_ratio:.2f} < {min_rr}")

        # ضرر روزانه
        daily_loss = context.get("daily_loss_amount", 0)
        max_daily_loss = context.get("max_daily_loss", float("inf"))
        risk.daily_loss_pass = daily_loss < max_daily_loss
        if not risk.daily_loss_pass:
            risk.rejection_reasons.append(f"حداکثر ضرر روزانه: {daily_loss:.2f}$")

        # تعداد معاملات همزمان
        open_trades = context.get("open_trades_count", 0)
        max_trades = context.get("max_simultaneous_trades", 3)
        risk.max_trades_pass = open_trades < max_trades
        if not risk.max_trades_pass:
            risk.rejection_reasons.append(f"تعداد معاملات باز: {open_trades}/{max_trades}")

        # نوسانات
        current_volatility = context.get("current_volatility", "medium")
        risk.volatility_pass = current_volatility != "extreme"

        # اسپرد
        current_spread = context.get("current_spread", 0)
        max_spread = context.get("max_allowed_spread", 30)
        risk.spread_pass = current_spread <= max_spread

        # درصد ریسک
        risk.risk_percent = context.get("risk_percent_per_trade", 1.0)

        # محاسبه امتیاز ریسک
        passed_checks = sum([
            risk.rr_pass, risk.daily_loss_pass,
            risk.max_trades_pass, risk.volatility_pass, risk.spread_pass
        ])
        risk.risk_score = (passed_checks / 5) * 100

        result.stage_log.append(
            f"  RR: {risk.risk_reward_ratio:.2f} | "
            f"چک‌های پاس: {passed_checks}/5 | "
            f"امتیاز: {risk.risk_score:.1f}"
        )

        return risk

    def _stage_final_decision(self, result: DecisionResult):
        """
        مرحله ۶: تصمیم نهایی با وزن‌دهی

        جمع‌بندی تمام امتیازات و تصمیم‌گیری نهایی
        """
        result.stage_log.append("🎯 مرحله ۶: تصمیم نهایی")

        # محاسبه امتیاز کلی با وزن‌دهی
        result.total_score = (
            result.mtf_score * SCORE_WEIGHTS["mtf_alignment"] +
            result.smc_score * SCORE_WEIGHTS["smc"] +
            result.pa_score * SCORE_WEIGHTS["price_action"] +
            result.risk_score * SCORE_WEIGHTS["risk_quality"] +
            result.session_score * SCORE_WEIGHTS["session"]
        )

        # تعیین جهت پیشنهادی
        suggested_direction = self._determine_suggested_direction(result)
        result.suggested_direction = suggested_direction

        # تصمیم نهایی
        if result.total_score >= self.minimum_entry_score:
            if suggested_direction == "bullish":
                result.decision = "BUY"
            elif suggested_direction == "bearish":
                result.decision = "SELL"
            else:
                result.decision = "NO_TRADE"
                result.rejection_reason = "جهت نامشخص"
        else:
            result.decision = "NO_TRADE"
            result.rejection_reason = (
                f"امتیاز ناکافی: {result.total_score:.1f} < {self.minimum_entry_score}"
            )

        result.stage_log.append(
            f"  امتیاز کل: {result.total_score:.1f} | "
            f"حداقل: {self.minimum_entry_score} | "
            f"تصمیم: {result.decision}"
        )

    def _determine_suggested_direction(self, result: DecisionResult) -> str:
        """تعیین جهت پیشنهادی از ترکیب MTF و PA و SMC"""
        bullish_votes = 0
        bearish_votes = 0

        # رأی MTF
        if result.mtf_result:
            if result.mtf_result.overall_direction == TrendDirection.BULLISH:
                bullish_votes += 3
            elif result.mtf_result.overall_direction == TrendDirection.BEARISH:
                bearish_votes += 3

        # رأی SMC
        if result.smc_result:
            if result.smc_result.bos_confirmed and result.smc_result.liquidity_sweep_confirmed:
                # جهت از BOS و Liquidity تعیین می‌شود
                smc_raw = {}
                if result.mtf_result and result.mtf_result.ltf.raw_data.get("smc"):
                    smc_raw = result.mtf_result.ltf.raw_data["smc"]

                bos_dir = smc_raw.get("market_structure", {}).get("last_bos_direction", "")
                if bos_dir == "bullish":
                    bullish_votes += 2
                elif bos_dir == "bearish":
                    bearish_votes += 2

        # رأی PA
        if result.pa_result:
            if result.pa_result.dominant_direction == "bullish":
                bullish_votes += 1
            elif result.pa_result.dominant_direction == "bearish":
                bearish_votes += 1

        if bullish_votes > bearish_votes:
            return "bullish"
        elif bearish_votes > bullish_votes:
            return "bearish"
        else:
            return "neutral"
