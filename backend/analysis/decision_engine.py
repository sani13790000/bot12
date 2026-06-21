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
  - تعداد معاملات هم‌زمان

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
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TrendDirection(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    UNDEFINED = "undefined"


@dataclass
class TimeframeAnalysis:
    """نتیجه تحلیل یک تایم‌فریم"""
    timeframe: str = ""
    level: TimeframeLevel = TimeframeLevel.MEDIUM
    trend: TrendDirection = TrendDirection.UNDEFINED
    trend_strength: float = 0.0
    structure_event: Optional[str] = None
    key_level: Optional[float] = None
    score: float = 0.0
    weight: float = 1.0
    notes: List[str] = field(default_factory=list)


@dataclass
class SMCScoreResult:
    """نتیجه امتیازدهی SMC"""
    total_score: float = 0.0
    order_block_score: float = 0.0
    fvg_score: float = 0.0
    bos_score: float = 0.0
    choch_score: float = 0.0
    liquidity_score: float = 0.0
    premium_discount_score: float = 0.0
    weighted_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    minimum_required: float = 0.0
    notes: List[str] = field(default_factory=list)


@dataclass
class PAScoreResult:
    """نتیجه امتیازدهی Price Action"""
    total_score: float = 0.0
    candle_pattern_score: float = 0.0
    breakout_score: float = 0.0
    compression_score: float = 0.0
    momentum_score: float = 0.0
    weighted_score: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    passed: bool = False
    minimum_required: float = 0.0
    patterns_found: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class MultiTimeframeResult:
    """نتیجه تحلیل چند تایم‌فریمه"""
    aligned: bool = False
    alignment_score: float = 0.0
    htf: Optional[TimeframeAnalysis] = None
    mtf: Optional[TimeframeAnalysis] = None
    ltf: Optional[TimeframeAnalysis] = None
    direction: TrendDirection = TrendDirection.UNDEFINED
    notes: List[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
    """ارزیابی ریسک معامله"""
    passed: bool = False
    risk_reward_ratio: float = 0.0
    max_daily_loss_reached: bool = False
    max_positions_reached: bool = False
    position_size: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class DecisionResult:
    """نتیجه نهایی تصمیم‌گیری"""
    symbol: str = ""
    timeframe: str = ""
    decision: str = "NO_TRADE"
    direction: str = "neutral"
    total_score: float = 0.0
    minimum_required_score: float = 0.0
    allowed: bool = False

    # امتیازات مراحل
    mtf_score: float = 0.0
    smc_score: float = 0.0
    pa_score: float = 0.0

    # سطوح قیمتی
    entry_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None

    # متادیتا
    analysis_time: str = ""
    stages_passed: List[str] = field(default_factory=list)
    stages_failed: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    blocked_reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    # نتایج مراحل
    mtf_result: Optional[MultiTimeframeResult] = None
    smc_result: Optional[SMCScoreResult] = None
    pa_result: Optional[PAScoreResult] = None
    risk_assessment: Optional[RiskAssessment] = None


# ============================================================
# ثوابت
# ============================================================
MINIMUM_ENTRY_SCORE = 65.0

MODULE_WEIGHTS = {
    "multi_timeframe": 0.30,
    "smc": 0.40,
    "price_action": 0.30,
}

SMC_COMPONENT_WEIGHTS = {
    "order_block": 0.30,
    "fvg": 0.20,
    "bos_choch": 0.25,
    "liquidity": 0.15,
    "premium_discount": 0.10,
}

PA_COMPONENT_WEIGHTS = {
    "candle_pattern": 0.35,
    "breakout": 0.30,
    "compression": 0.20,
    "momentum": 0.15,
}


class MultiTimeframeEngine:
    """
    موتور تحلیل چند تایم‌فریمه
    """

    # وزن‌های پیش‌فرض برای هر سطح تایم‌فریم
    HTF_WEIGHT = 0.40
    MTF_WEIGHT = 0.35
    LTF_WEIGHT = 0.25

    # آستانه تراز بودن
    ALIGNMENT_THRESHOLD = 0.60

    def __init__(self) -> None:
        self._timeframe_map = {
            # LTF (Low Timeframe)
            "M1": (TimeframeLevel.LOW, 1),
            "M5": (TimeframeLevel.LOW, 5),
            "M15": (TimeframeLevel.LOW, 15),
            "M30": (TimeframeLevel.LOW, 30),
            # MTF (Medium Timeframe)
            "H1": (TimeframeLevel.MEDIUM, 60),
            "H4": (TimeframeLevel.MEDIUM, 240),
            # HTF (High Timeframe)
            "D1": (TimeframeLevel.HIGH, 1440),
            "W1": (TimeframeLevel.HIGH, 10080),
            "MN1": (TimeframeLevel.HIGH, 43200),
        }

    def analyze(
        self,
        symbol: str,
        base_timeframe: str,
        smc_results: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> MultiTimeframeResult:
        """
        تحلیل چند تایم‌فریمه

        پارامترها:
            symbol: نماد معاملاتی
            base_timeframe: تایم‌فریم پایه (LTF)
            smc_results: نتایج کامل موتور SMC
            market_context: اطلاعات بازار
        """
        result = MultiTimeframeResult()

        try:
            # تعیین تایم‌فریم‌های بالاتر
            ltf_name, htf_name, mtf_name = self._get_timeframe_hierarchy(base_timeframe)

            # تحلیل هر سطح
            ltf_data = self._extract_timeframe_data(ltf_name, smc_results, market_context)
            mtf_data = self._extract_timeframe_data(mtf_name, smc_results, market_context)
            htf_data = self._extract_timeframe_data(htf_name, smc_results, market_context)

            result.ltf = self._build_analysis(ltf_name, TimeframeLevel.LOW, ltf_data)
            result.mtf = self._build_analysis(mtf_name, TimeframeLevel.MEDIUM, mtf_data)
            result.htf = self._build_analysis(htf_name, TimeframeLevel.HIGH, htf_data)

            # بررسی تراز بودن
            alignment_score = self._calculate_alignment(
                result.htf, result.mtf, result.ltf
            )
            result.alignment_score = alignment_score
            result.aligned = alignment_score >= self.ALIGNMENT_THRESHOLD

            # جهت کلی
            result.direction = self._determine_overall_direction(
                result.htf, result.mtf, result.ltf
            )

            if result.aligned:
                result.notes.append(
                    f"تراز چند تایم‌فریمه تایید شد (امتیاز: {alignment_score:.1%})"
                )
            else:
                result.notes.append(
                    f"عدم تراز تایم‌فریم‌ها (امتیاز: {alignment_score:.1%})"
                )

        except Exception as e:
            logger.exception(f"خطا در تحلیل چند تایم‌فریمه: {e}")
            result.notes.append(f"خطا در تحلیل: {str(e)}")

        return result

    def _get_timeframe_hierarchy(
        self, base_tf: str
    ) -> Tuple[str, str, str]:
        """تعیین سلسله‌مراتب تایم‌فریم‌ها"""
        hierarchy = {
            "M1":  ("M1", "M5",  "H1"),
            "M5":  ("M5", "H1",  "H4"),
            "M15": ("M15", "H1", "H4"),
            "M30": ("M30", "H4", "D1"),
            "H1":  ("H1",  "H4", "D1"),
            "H4":  ("H4",  "D1", "W1"),
            "D1":  ("D1",  "W1", "MN1"),
        }
        return hierarchy.get(base_tf, ("M15", "H1", "H4"))

    def _extract_timeframe_data(
        self,
        timeframe: str,
        smc_results: Dict[str, Any],
        market_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """استخراج داده‌های یک تایم‌فریم از نتایج"""
        # جستجو در نتایج SMC
        tf_data = smc_results.get(timeframe, smc_results.get("current", {}))
        ctx_data = market_context.get(timeframe, market_context)

        return {
            "trend": tf_data.get("trend") or ctx_data.get("trend", "ranging"),
            "trend_strength": float(
                tf_data.get("trend_strength") or ctx_data.get("trend_strength", 0.5)
            ),
            "structure_event": tf_data.get("structure_event") or ctx_data.get("structure_event"),
            "key_level": tf_data.get("key_level") or ctx_data.get("key_level"),
            "score": float(tf_data.get("score", 0.5)),
        }

    def _build_analysis(
        self,
        timeframe: str,
        level: TimeframeLevel,
        data: Dict[str, Any],
    ) -> TimeframeAnalysis:
        """ساخت شیء تحلیل تایم‌فریم"""
        trend_str = str(data.get("trend", "ranging")).lower()
        trend_map = {
            "bullish": TrendDirection.BULLISH,
            "bearish": TrendDirection.BEARISH,
            "ranging": TrendDirection.RANGING,
        }
        trend = trend_map.get(trend_str, TrendDirection.UNDEFINED)

        weight_map = {
            TimeframeLevel.HIGH: self.HTF_WEIGHT,
            TimeframeLevel.MEDIUM: self.MTF_WEIGHT,
            TimeframeLevel.LOW: self.LTF_WEIGHT,
        }

        return TimeframeAnalysis(
            timeframe=timeframe,
            level=level,
            trend=trend,
            trend_strength=data.get("trend_strength", 0.5),
            structure_event=data.get("structure_event"),
            key_level=data.get("key_level"),
            score=data.get("score", 0.5),
            weight=weight_map.get(level, 1.0),
        )

    def _calculate_alignment(
        self,
        htf: TimeframeAnalysis,
        mtf: TimeframeAnalysis,
        ltf: TimeframeAnalysis,
    ) -> float:
        """محاسبه درجه تراز بودن تایم‌فریم‌ها"""
        trends = [htf.trend, mtf.trend, ltf.trend]

        bullish_count = trends.count(TrendDirection.BULLISH)
        bearish_count = trends.count(TrendDirection.BEARISH)

        if bullish_count == 3:
            base_score = 1.0
        elif bearish_count == 3:
            base_score = 1.0
        elif bullish_count == 2:
            base_score = 0.75
        elif bearish_count == 2:
            base_score = 0.75
        else:
            base_score = 0.30

        # وزن‌دهی با قدرت روند
        strength_factor = (
            htf.trend_strength * self.HTF_WEIGHT +
            mtf.trend_strength * self.MTF_WEIGHT +
            ltf.trend_strength * self.LTF_WEIGHT
        )

        return base_score * (0.7 + 0.3 * strength_factor)

    def _determine_overall_direction(
        self,
        htf: TimeframeAnalysis,
        mtf: TimeframeAnalysis,
        ltf: TimeframeAnalysis,
    ) -> TrendDirection:
        """تعیین جهت کلی بازار"""
        # HTF اولویت اصلی دارد
        if htf.trend in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            return htf.trend

        # اگر HTF ranging بود، MTF تصمیم می‌گیرد
        if mtf.trend in (TrendDirection.BULLISH, TrendDirection.BEARISH):
            return mtf.trend

        return TrendDirection.RANGING


# ============================================================
# کلاس اصلی موتور
# ============================================================

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
        self.minimum_entry_score = minimum_entry_score
        self.mtf_engine = MultiTimeframeEngine()

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
        result = DecisionResult(
            symbol=symbol,
            timeframe=timeframe,
            minimum_required_score=self.minimum_entry_score,
            analysis_time=datetime.now(timezone.utc).isoformat(),
        )

        try:
            # مرحله ۱: فیلتر اولیه
            if not self._initial_filter(symbol, market_context, result):
                return result

            # مرحله ۲: تحلیل Multi-Timeframe
            if self.enabled_modules.get("multi_timeframe", True):
                mtf_result = self.mtf_engine.analyze(
                    symbol, timeframe, smc_results, market_context
                )
                result.mtf_result = mtf_result

                if not mtf_result.aligned:
                    result.stages_failed.append(DecisionStage.MULTI_TIMEFRAME.value)
                    result.blocked_reasons.append("عدم تراز تایم‌فریم‌ها")
                    return result

                result.mtf_score = mtf_result.alignment_score * 100
                result.stages_passed.append(DecisionStage.MULTI_TIMEFRAME.value)

            # مرحله ۳: امتیازدهی SMC
            if self.enabled_modules.get("smc", True):
                smc_score_result = self._score_smc(smc_results, market_context)
                result.smc_result = smc_score_result

                if not smc_score_result.passed:
                    result.stages_failed.append(DecisionStage.SMC_SCORING.value)
                    result.blocked_reasons.append(
                        f"امتیاز SMC ناکافی: {smc_score_result.total_score:.1f}"
                    )
                    return result

                result.smc_score = smc_score_result.weighted_score
                result.stages_passed.append(DecisionStage.SMC_SCORING.value)

            # مرحله ۴: امتیازدهی Price Action
            if self.enabled_modules.get("price_action", True):
                pa_score_result = self._score_pa(pa_results)
                result.pa_result = pa_score_result

                if not pa_score_result.passed:
                    result.stages_failed.append(DecisionStage.PRICE_ACTION_SCORING.value)
                    result.blocked_reasons.append(
                        f"امتیاز PA ناکافی: {pa_score_result.total_score:.1f}"
                    )
                    return result

                result.pa_score = pa_score_result.weighted_score
                result.stages_passed.append(DecisionStage.PRICE_ACTION_SCORING.value)

            # مرحله ۵: فیلتر ریسک
            if self.enabled_modules.get("risk_filter", True):
                risk_result = self._assess_risk(symbol, market_context, result)
                result.risk_assessment = risk_result

                if not risk_result.passed:
                    result.stages_failed.append(DecisionStage.RISK_FILTER.value)
                    result.blocked_reasons.extend(risk_result.notes)
                    return result

                result.stages_passed.append(DecisionStage.RISK_FILTER.value)

            # مرحله ۶: تصمیم نهایی
            total_score = self._calculate_total_score(result)
            result.total_score = total_score

            if total_score >= self.minimum_entry_score:
                direction = self._determine_direction(result)
                result.direction = direction
                result.decision = "BUY" if direction == "bullish" else "SELL"
                result.allowed = True
                result.stages_passed.append(DecisionStage.FINAL_DECISION.value)
                result.reasons.append(
                    f"امتیاز کافی: {total_score:.1f} >= {self.minimum_entry_score}"
                )
            else:
                result.stages_failed.append(DecisionStage.FINAL_DECISION.value)
                result.blocked_reasons.append(
                    f"امتیاز ناکافی: {total_score:.1f} < {self.minimum_entry_score}"
                )

        except Exception as e:
            logger.exception(f"خطا در موتور تصمیم‌گیری: {e}")
            result.blocked_reasons.append(f"خطای داخلی: {str(e)}")

        return result

    def _initial_filter(
        self,
        symbol: str,
        market_context: Dict[str, Any],
        result: DecisionResult
    ) -> bool:
        """فیلتر اولیه - بررسی شرایط پایه"""
        # بررسی نوسانات
        volatility = market_context.get("volatility", 0.5)
        if volatility > 0.95:
            result.blocked_reasons.append("نوسانات بیش از حد")
            result.stages_failed.append(DecisionStage.INITIAL_FILTER.value)
            return False

        # بررسی ساعت معاملاتی
        trading_allowed = market_context.get("trading_session_active", True)
        if not trading_allowed:
            result.blocked_reasons.append("خارج از ساعت معاملاتی")
            result.stages_failed.append(DecisionStage.INITIAL_FILTER.value)
            return False

        result.stages_passed.append(DecisionStage.INITIAL_FILTER.value)
        return True

    def _score_smc(
        self,
        smc_results: Dict[str, Any],
        market_context: Dict[str, Any]
    ) -> SMCScoreResult:
        """امتیازدهی Smart Money Concepts"""
        score_result = SMCScoreResult(
            minimum_required=40.0
        )

        # Order Block
        ob_data = smc_results.get("order_blocks", {})
        ob_score = min(
            float(ob_data.get("score", 0)) * 100,
            100.0
        ) if ob_data else 0.0
        score_result.order_block_score = ob_score

        # FVG
        fvg_data = smc_results.get("fvg", {})
        fvg_score = min(
            float(fvg_data.get("score", 0)) * 100,
            100.0
        ) if fvg_data else 0.0
        score_result.fvg_score = fvg_score

        # BOS/CHOCH
        structure = smc_results.get("structure", {})
        bos_score = 0.0
        if structure.get("bos_detected"):
            bos_score += 50.0
        if structure.get("choch_detected"):
            bos_score += 50.0
        score_result.bos_score = min(bos_score, 100.0)
        score_result.choch_score = min(bos_score, 100.0)

        # Liquidity
        liq_data = smc_results.get("liquidity", {})
        liq_score = min(
            float(liq_data.get("score", 0)) * 100,
            100.0
        ) if liq_data else 0.0
        score_result.liquidity_score = liq_score

        # Premium/Discount
        pd_zone = market_context.get("premium_discount", "neutral")
        pd_score = 80.0 if pd_zone in ("discount", "premium") else 40.0
        score_result.premium_discount_score = pd_score

        # محاسبه امتیاز وزن‌دهی شده
        weighted = (
            ob_score * SMC_COMPONENT_WEIGHTS["order_block"] +
            fvg_score * SMC_COMPONENT_WEIGHTS["fvg"] +
            score_result.bos_score * SMC_COMPONENT_WEIGHTS["bos_choch"] +
            liq_score * SMC_COMPONENT_WEIGHTS["liquidity"] +
            pd_score * SMC_COMPONENT_WEIGHTS["premium_discount"]
        )
        score_result.total_score = weighted
        score_result.weighted_score = weighted
        score_result.passed = weighted >= score_result.minimum_required

        return score_result

    def _score_pa(self, pa_results: Dict[str, Any]) -> PAScoreResult:
        """امتیازدهی Price Action"""
        score_result = PAScoreResult(minimum_required=35.0)

        # الگوهای شمعی
        patterns = pa_results.get("patterns", [])
        candle_score = min(len(patterns) * 25.0, 100.0)
        score_result.candle_pattern_score = candle_score
        score_result.patterns_found = [str(p) for p in patterns]

        # Breakout
        breakout = pa_results.get("breakout", {})
        breakout_score = float(breakout.get("score", 0)) * 100 if breakout else 0.0
        score_result.breakout_score = min(breakout_score, 100.0)

        # Compression
        compression = pa_results.get("compression", {})
        compression_score = float(compression.get("score", 0)) * 100 if compression else 0.0
        score_result.compression_score = min(compression_score, 100.0)

        # Momentum
        momentum = pa_results.get("momentum", {})
        momentum_score = float(momentum.get("score", 0)) * 100 if momentum else 0.0
        score_result.momentum_score = min(momentum_score, 100.0)

        # امتیاز وزن‌دهی شده
        weighted = (
            candle_score * PA_COMPONENT_WEIGHTS["candle_pattern"] +
            score_result.breakout_score * PA_COMPONENT_WEIGHTS["breakout"] +
            score_result.compression_score * PA_COMPONENT_WEIGHTS["compression"] +
            momentum_score * PA_COMPONENT_WEIGHTS["momentum"]
        )
        score_result.total_score = weighted
        score_result.weighted_score = weighted
        score_result.passed = weighted >= score_result.minimum_required

        return score_result

    def _assess_risk(
        self,
        symbol: str,
        market_context: Dict[str, Any],
        result: DecisionResult
    ) -> RiskAssessment:
        """ارزیابی ریسک معامله"""
        assessment = RiskAssessment()

        # بررسی نسبت R:R
        entry = market_context.get("entry_price", 0.0)
        sl = market_context.get("stop_loss")
        tp = market_context.get("take_profit")

        if entry and sl and tp:
            risk = abs(entry - sl)
            reward = abs(tp - entry)
            if risk > 0:
                rr_ratio = reward / risk
                assessment.risk_reward_ratio = rr_ratio
                if rr_ratio < 1.5:
                    assessment.notes.append(f"نسبت R:R ناکافی: {rr_ratio:.2f}")
                    assessment.passed = False
                    return assessment
            result.entry_price = entry
            result.stop_loss = sl
            result.take_profit_1 = tp

        # بررسی حداکثر ضرر روزانه
        daily_loss_pct = market_context.get("daily_loss_pct", 0.0)
        if daily_loss_pct >= 3.0:
            assessment.max_daily_loss_reached = True
            assessment.notes.append("حداکثر ضرر روزانه رسیده")
            assessment.passed = False
            return assessment

        # بررسی تعداد معاملات
        open_positions = market_context.get("open_positions_count", 0)
        max_positions = market_context.get("max_positions", 5)
        if open_positions >= max_positions:
            assessment.max_positions_reached = True
            assessment.notes.append(f"حداکثر معاملات همزمان: {open_positions}/{max_positions}")
            assessment.passed = False
            return assessment

        assessment.passed = True
        assessment.notes.append("ریسک در محدوده مجاز")
        return assessment

    def _calculate_total_score(self, result: DecisionResult) -> float:
        """محاسبه امتیاز کل وزن‌دهی شده"""
        total = 0.0
        if result.mtf_score > 0:
            total += result.mtf_score * MODULE_WEIGHTS["multi_timeframe"]
        if result.smc_score > 0:
            total += result.smc_score * MODULE_WEIGHTS["smc"]
        if result.pa_score > 0:
            total += result.pa_score * MODULE_WEIGHTS["price_action"]
        return total

    def _determine_direction(
        self, result: DecisionResult
    ) -> str:
        """تعیین جهت معامله"""
        if result.mtf_result and result.mtf_result.direction == TrendDirection.BULLISH:
            return "bullish"
        if result.mtf_result and result.mtf_result.direction == TrendDirection.BEARISH:
            return "bearish"
        return "bullish"  # default


# =============================================================================
# =================== CONTRACT LAYER (Service Interface) ======================
# =============================================================================
# این بخش اشیاء قراردادی را تعریف می‌کند که decision_service.py با آن‌ها کار می‌کند.
# make_decision() به‌عنوان bridge بین این لایه و موتور داخلی decide() عمل می‌کند.
# Phase D Fix (TECH-6): _datetime.utcnow() -> _datetime.now(_timezone.utc)
# =============================================================================

from dataclasses import dataclass as _dataclass
from typing import List as _List, Optional as _Optional, Dict as _Dict, Any as _Any
from datetime import datetime as _datetime, timezone as _timezone
from enum import Enum as _Enum


# --- Enums ---

class ReasonCode(_Enum):
    MTF_ALIGNED = "mtf_aligned"
    SMC_CONFIRMED = "smc_confirmed"
    PA_CONFIRMED = "pa_confirmed"
    RISK_PASSED = "risk_passed"
    SESSION_ACTIVE = "session_active"
    LIQUIDITY_SWEPT = "liquidity_swept"
    ORDER_BLOCK_PRESENT = "order_block_present"
    FVG_PRESENT = "fvg_present"
    HIGH_CONFLUENCE = "high_confluence"


class BlockedReason(_Enum):
    MTF_FAILED = "mtf_failed"
    SMC_FAILED = "smc_failed"
    PA_FAILED = "pa_failed"
    RISK_FAILED = "risk_failed"
    SESSION_CLOSED = "session_closed"
    LOW_SCORE = "low_score"
    SYMBOL_BLOCKED = "symbol_blocked"
    LICENSE_INVALID = "license_invalid"
    VOLATILITY_TOO_HIGH = "volatility_too_high"


@_dataclass
class SMCContext:
    trend: _Any = "ranging"
    trend_score: float = 0.0
    structure_event: _Optional[str] = None
    structure_direction: _Optional[str] = None
    structure_level: _Optional[float] = None
    liquidity_swept: bool = False
    liquidity_direction: _Optional[str] = None
    premium_discount: str = "neutral"
    order_blocks: _List[_Dict[str, _Any]] = None
    fvgs: _List[_Dict[str, _Any]] = None
    swing_high: _Optional[float] = None
    swing_low: _Optional[float] = None

    def __post_init__(self):
        if self.order_blocks is None:
            self.order_blocks = []
        if self.fvgs is None:
            self.fvgs = []


@_dataclass
class PriceActionContext:
    direction: _Any = "neutral"
    direction_score: float = 0.0
    patterns: _List[str] = None
    candle_strength: str = "none"

    def __post_init__(self):
        if self.patterns is None:
            self.patterns = []


@_dataclass
class SessionContext:
    current_session: _Any = "closed"
    killzone_active: bool = False
    killzone_name: _Optional[str] = None
    session_score: float = 0.0


@_dataclass
class LicenseContext:
    is_valid: bool = True
    is_expired: bool = False
    account_id: _Optional[str] = None
    license_type: str = "standard"
    expires_at: _Optional[str] = None


@_dataclass
class RiskContext:
    available_margin: _Optional[float] = None
    risk_per_trade: float = 0.01
    max_daily_loss: float = 0.03
    open_positions: int = 0
    max_positions: int = 5
    daily_loss_pct: float = 0.0


@_dataclass
class SymbolPolicy:
    symbol: str = ""
    is_allowed: bool = True
    min_score_override: _Optional[float] = None
    max_spread_pips: _Optional[float] = None
    blocked_reason: _Optional[str] = None


@_dataclass
class VolatilityContext:
    atr: float = 0.0
    atr_pct: float = 0.0
    volatility_level: _Any = "medium"
    is_high_impact_news: bool = False
    news_minutes_away: int = 999


@_dataclass
class MultiTimeframeContext:
    htf_trend: _Any = "ranging"
    htf_score: float = 0.0
    mtf_trend: _Any = "ranging"
    mtf_score: float = 0.0
    ltf_trigger: _Optional[str] = None
    aligned: bool = False
    alignment_score: float = 0.0


@_dataclass
class LiquidityContext:
    buy_side_liquidity: _List[float] = None
    sell_side_liquidity: _List[float] = None
    nearest_bsl: _Optional[float] = None
    nearest_ssl: _Optional[float] = None
    liquidity_swept: bool = False
    sweep_direction: _Optional[str] = None
    inducement_present: bool = False

    def __post_init__(self):
        if self.buy_side_liquidity is None:
            self.buy_side_liquidity = []
        if self.sell_side_liquidity is None:
            self.sell_side_liquidity = []


@_dataclass
class DecisionInput:
    symbol: str = ""
    timeframe: str = ""
    smc_context: SMCContext = None
    price_action_context: PriceActionContext = None
    session_context: SessionContext = None
    license_context: LicenseContext = None
    risk_context: RiskContext = None
    symbol_policy: SymbolPolicy = None
    volatility_context: VolatilityContext = None
    mtf_context: MultiTimeframeContext = None
    liquidity_context: LiquidityContext = None

    def __post_init__(self):
        if self.smc_context is None:
            self.smc_context = SMCContext()
        if self.price_action_context is None:
            self.price_action_context = PriceActionContext()
        if self.session_context is None:
            self.session_context = SessionContext()
        if self.license_context is None:
            self.license_context = LicenseContext()
        if self.risk_context is None:
            self.risk_context = RiskContext()
        if self.symbol_policy is None:
            self.symbol_policy = SymbolPolicy(symbol=self.symbol)
        if self.volatility_context is None:
            self.volatility_context = VolatilityContext()
        if self.mtf_context is None:
            self.mtf_context = MultiTimeframeContext()
        if self.liquidity_context is None:
            self.liquidity_context = LiquidityContext()


@_dataclass
class TradingLevels:
    entry_zone: float = 0.0
    entry_zone_high: float = 0.0
    entry_zone_low: float = 0.0
    stop_loss: _Optional[float] = None
    take_profit_1: _Optional[float] = None
    take_profit_2: _Optional[float] = None
    take_profit_3: _Optional[float] = None
    invalidation_level: _Optional[float] = None
    risk_reward_ratio: float = 0.0


@_dataclass
class RiskProfile:
    risk_level: str = "medium"
    position_size: float = 0.0
    max_loss_amount: float = 0.0
    potential_profit: float = 0.0
    risk_reward_ratio: float = 0.0


@_dataclass
class DecisionOutput:
    symbol: str = ""
    timeframe: str = ""
    created_at: _datetime = None
    decision: _Any = "NO_TRADE"
    direction: _Any = "neutral"
    confidence_score: float = 0.0
    quality_score: float = 0.0
    allowed: bool = False
    reason_codes: _List[ReasonCode] = None
    reasons_persian: _List[str] = None
    blocked_reasons: _List[BlockedReason] = None
    score_breakdown: _Dict[str, float] = None
    metadata: _Dict[str, _Any] = None
    trading_levels: _Optional[TradingLevels] = None
    risk_profile: _Optional[RiskProfile] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = _datetime.now(_timezone.utc)
        if self.reason_codes is None:
            self.reason_codes = []
        if self.reasons_persian is None:
            self.reasons_persian = []
        if self.blocked_reasons is None:
            self.blocked_reasons = []
        if self.score_breakdown is None:
            self.score_breakdown = {}
        if self.metadata is None:
            self.metadata = {}


# =============================================================================
# Bridge method -- injected into DecisionEngine at module load
# =============================================================================

def _make_decision(self, decision_input: "DecisionInput") -> "DecisionOutput":
    """
    Bridge: DecisionInput -> decide() -> DecisionOutput
    Phase D Fix (TECH-6): uses _datetime.now(_timezone.utc)
    """
    smc = decision_input.smc_context
    pa = decision_input.price_action_context
    session = decision_input.session_context
    liq = decision_input.liquidity_context
    vol = decision_input.volatility_context
    risk = decision_input.risk_context
    policy = decision_input.symbol_policy
    license_ = decision_input.license_context
    mtf = decision_input.mtf_context

    # License check
    if not license_.is_valid or license_.is_expired:
        return _build_blocked_output(
            decision_input,
            blocked=[BlockedReason.LICENSE_INVALID],
            reasons=["مجوز نامعتبر یا منقضی شده"]
        )

    # Symbol policy check
    if not policy.is_allowed:
        return _build_blocked_output(
            decision_input,
            blocked=[BlockedReason.SYMBOL_BLOCKED],
            reasons=[policy.blocked_reason or "نماد مسدود است"]
        )

    # Build smc_results dict for decide()
    smc_results = {
        "trend": getattr(smc.trend, "value", str(smc.trend)),
        "trend_strength": smc.trend_score / 100.0,
        "order_blocks": {"score": len(smc.order_blocks) / 5.0},
        "fvg": {"score": len(smc.fvgs) / 3.0},
        "structure": {
            "bos_detected": smc.structure_event in ("BOS", "MSS"),
            "choch_detected": smc.structure_event == "CHOCH",
        },
        "liquidity": {"score": 0.8 if liq.liquidity_swept else 0.3},
        "current": {
            "trend": getattr(smc.trend, "value", str(smc.trend)),
            "trend_strength": smc.trend_score / 100.0,
        },
    }

    # MTF context
    if mtf and mtf.aligned:
        smc_results["H4"] = {
            "trend": getattr(mtf.htf_trend, "value", str(mtf.htf_trend)),
            "trend_strength": mtf.htf_score / 100.0,
            "score": mtf.htf_score / 100.0,
        }

    # Build pa_results
    pa_results = {
        "patterns": pa.patterns or [],
        "breakout": {"score": pa.direction_score / 100.0 if pa.direction_score > 50 else 0.0},
        "compression": {"score": 0.5},
        "momentum": {"score": pa.direction_score / 100.0},
    }

    # Market context
    market_context = {
        "volatility": vol.atr_pct if vol else 0.3,
        "trading_session_active": session.killzone_active or session.session_score > 0,
        "premium_discount": smc.premium_discount,
        "daily_loss_pct": risk.daily_loss_pct,
        "open_positions_count": risk.open_positions,
        "max_positions": risk.max_positions,
    }

    # Run engine
    result = self.decide(
        symbol=decision_input.symbol,
        timeframe=decision_input.timeframe,
        smc_results=smc_results,
        pa_results=pa_results,
        market_context=market_context,
    )

    return _result_to_output(result, decision_input, risk)


def _build_blocked_output(
    decision_input: "DecisionInput",
    blocked: _List["BlockedReason"],
    reasons: _List[str],
) -> "DecisionOutput":
    """ساخت DecisionOutput برای حالت رد شده"""
    try:
        from ..core.enums import DecisionAction, DecisionDirection
        decision_val = DecisionAction.NO_TRADE
        direction_val = DecisionDirection.NEUTRAL
    except Exception:
        decision_val = "NO_TRADE"
        direction_val = "neutral"

    return DecisionOutput(
        symbol=decision_input.symbol,
        timeframe=decision_input.timeframe,
        created_at=_datetime.now(_timezone.utc),  # FIX TECH-6
        decision=decision_val,
        direction=direction_val,
        confidence_score=0.0,
        quality_score=0.0,
        allowed=False,
        blocked_reasons=blocked,
        reasons_persian=reasons,
        score_breakdown={},
        metadata={}
    )


def _result_to_output(
    result: "DecisionResult",
    decision_input: "DecisionInput",
    risk: "RiskContext"
) -> "DecisionOutput":
    """تبدیل DecisionResult داخلی به DecisionOutput قراردادی"""
    try:
        from ..core.enums import DecisionAction, DecisionDirection
        allowed = result.allowed
        if allowed:
            decision_val = (DecisionAction.BUY if result.direction == "bullish"
                           else DecisionAction.SELL)
            direction_val = (DecisionDirection.LONG if result.direction == "bullish"
                            else DecisionDirection.SHORT)
        else:
            decision_val = DecisionAction.NO_TRADE
            direction_val = DecisionDirection.NEUTRAL
    except Exception:
        allowed = result.allowed
        decision_val = result.decision
        direction_val = result.direction

    reason_codes = []
    reasons_persian = list(result.reasons)
    blocked_reasons = []
    score_breakdown = {
        "mtf_score": result.mtf_score,
        "smc_score": result.smc_score,
        "pa_score": result.pa_score,
        "total_score": result.total_score,
    }

    if result.mtf_score >= 60:
        reason_codes.append(ReasonCode.MTF_ALIGNED)
    if result.smc_score >= 40:
        reason_codes.append(ReasonCode.SMC_CONFIRMED)
    if result.pa_score >= 35:
        reason_codes.append(ReasonCode.PA_CONFIRMED)

    for br in result.blocked_reasons:
        if "MTF" in br or "تایم" in br:
            blocked_reasons.append(BlockedReason.MTF_FAILED)
        elif "SMC" in br:
            blocked_reasons.append(BlockedReason.SMC_FAILED)
        elif "PA" in br:
            blocked_reasons.append(BlockedReason.PA_FAILED)
        elif "ریسک" in br or "R:R" in br:
            blocked_reasons.append(BlockedReason.RISK_FAILED)
        elif "امتیاز" in br:
            blocked_reasons.append(BlockedReason.LOW_SCORE)

    trading_levels: _Optional[TradingLevels] = None
    if allowed and result.entry_price > 0:
        trading_levels = TradingLevels(
            entry_zone=result.entry_price,
            entry_zone_high=result.entry_price * 1.0005,
            entry_zone_low=result.entry_price * 0.9995,
            stop_loss=result.stop_loss,
            take_profit_1=result.take_profit_1,
            take_profit_2=result.take_profit_2,
            take_profit_3=result.take_profit_3,
            invalidation_level=result.stop_loss,
            risk_reward_ratio=(
                abs(result.take_profit_1 - result.entry_price) / abs(result.entry_price - result.stop_loss)
                if result.stop_loss and result.entry_price and result.stop_loss != result.entry_price
                else 0.0
            )
        )

    risk_profile: _Optional[RiskProfile] = None
    if allowed:
        margin = risk.available_margin or 1.0
        pos_size = round(margin * risk.risk_per_trade / max(
            abs(result.entry_price - result.stop_loss) * 100000 if result.stop_loss else 1, 1
        ), 2)
        rr = trading_levels.risk_reward_ratio if trading_levels else 0.0
        max_loss = round(margin * risk.risk_per_trade, 2)
        risk_profile = RiskProfile(
            risk_level=str(getattr(decision_input.volatility_context.volatility_level, "value", "medium")),
            position_size=pos_size,
            max_loss_amount=max_loss,
            potential_profit=round(max_loss * rr, 2),
            risk_reward_ratio=rr
        )

    return DecisionOutput(
        symbol=result.symbol,
        timeframe=result.timeframe,
        created_at=_datetime.now(_timezone.utc),  # FIX TECH-6
        decision=decision_val,
        direction=direction_val,
        confidence_score=min(result.total_score / 100.0, 1.0),
        quality_score=result.total_score,
        allowed=allowed,
        reason_codes=reason_codes,
        reasons_persian=reasons_persian,
        blocked_reasons=blocked_reasons,
        score_breakdown=score_breakdown,
        metadata={
            "analysis_time": result.analysis_time,
            "minimum_required_score": result.minimum_required_score,
        },
        trading_levels=trading_levels,
        risk_profile=risk_profile
    )


# تزریق make_decision به DecisionEngine
DecisionEngine.make_decision = _make_decision
