"""
موتور تصمیم‌گیری

این موتور تمام ورودی‌ها را جمع‌آوری و تصمیم نهایی را می‌گیرد:
- جمع‌آوری امتیازات SMC, Price Action, Liquidity, Session
- وزن‌دهی و محاسبه امتیاز کل
- اعمال فیلترها
- تولید سیگنال معاملاتی

نویسنده: MT5 Trading Team
تاریخ: 2026-06-12
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from ..core.enums import Decision, TradeQuality, Confidence, TradeDirection
from ..core.config import settings
from ..core.logger import get_logger

logger = get_logger("decision_engine")


# =====================================================
# ساختارهای داده
# =====================================================

@dataclass
class DecisionInput:
    """ورودی‌های موتور تصمیم"""
    smc_score: float
    smc_direction: str
    smc_details: Dict[str, Any] = field(default_factory=dict)

    price_action_score: float
    price_action_direction: str
    price_action_details: Dict[str, Any] = field(default_factory=dict)

    liquidity_score: float
    liquidity_details: Dict[str, Any] = field(default_factory=dict)

    mtf_score: float
    mtf_alignment: Dict[str, Any] = field(default_factory=dict)

    session_score: float
    session_details: Dict[str, Any] = field(default_factory=dict)

    volatility_score: float
    volatility_details: Dict[str, Any] = field(default_factory=dict)

    risk_check_passed: bool = True
    risk_details: Dict[str, Any] = field(default_factory=dict)

    current_price: float = 0.0


@dataclass
class DecisionOutput:
    """خروجی موتور تصمیم"""
    decision: Decision
    quality: TradeQuality
    total_score: float

    score_breakdown: Dict[str, float]
    direction: Optional[str]
    confidence: Confidence

    reasons: List[str]
    rejections: List[str]

    suggested_entry: Optional[float]
    suggested_sl: Optional[float]
    suggested_tp: Optional[float]
    risk_reward_ratio: Optional[float]

    generated_at: datetime
    valid_until: Optional[datetime]


# =====================================================
# موتور تصمیم‌گیری
# =====================================================

class DecisionEngine:
    """
    موتور تصمیم‌گیری چندلایه

    مراحل تصمیم:
    1. جمع‌آوری ورودی‌ها
    2. وزن‌دهی و محاسبه امتیاز کل
    3. بررسی فیلترها
    4. تعیین جهت
    5. تعیین کیفیت
    6. محاسبه قیمت‌های پیشنهادی
    7. تولید تصمیم نهایی
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        مقداردهی اولیه

        Args:
            config: تنظیمات شامل:
                - min_entry_score: حداقل امتیاز ورود
                - weights: وزن هر بخش
                - direction_consensus: حداقل توافق جهت
        """
        self.config = config or {}

        # آستانه‌ها
        self.min_entry_score = self.config.get("min_entry_score", settings.MIN_ENTRY_SCORE)
        self.excellent_threshold = self.config.get("excellent_threshold", settings.EXCELLENT_SCORE)
        self.good_threshold = self.config.get("good_threshold", settings.GOOD_SCORE)
        self.moderate_threshold = self.config.get("moderate_threshold", settings.MODERATE_SCORE)

        # وزن‌ها
        self.weights = self.config.get("weights", {
            "smc": settings.SMC_WEIGHT,
            "price_action": settings.PRICE_ACTION_WEIGHT,
            "liquidity": settings.LIQUIDITY_WEIGHT,
            "mtf": settings.MTF_WEIGHT,
            "session": settings.SESSION_WEIGHT,
            "volatility": settings.VOLATILITY_WEIGHT
        })

        # حداقل توافق جهت
        self.direction_consensus = self.config.get("direction_consensus", 0.6)

        # سیگنال‌های اخیر
        self.recent_decisions: List[DecisionOutput] = []

        logger.info(f"موتور تصمیم‌گیری مقداردهی شد. حداقل امتیاز: {self.min_entry_score}")

    def make_decision(self, inputs: DecisionInput) -> DecisionOutput:
        """
        اتخاذ تصمیم معاملاتی

        Args:
            inputs: تمام ورودی‌های تحلیل

        Returns:
            DecisionOutput: تصمیم نهایی
        """
        logger.info("شروع فرآیند تصمیم‌گیری...")

        # مرحله 1: محاسبه امتیاز وزنی
        weighted_scores = self._calculate_weighted_scores(inputs)
        total_score = sum(weighted_scores.values())

        logger.debug(f"امتیاز کل: {total_score:.2f}")

        # مرحله 2: تعیین جهت
        direction = self._determine_direction(inputs)

        # مرحله 3: بررسی فیلترها
        passed, rejections = self._apply_filters(inputs, direction, total_score)

        if not passed:
            logger.info(f"تصمیم: NO TRADE - {', '.join(rejections)}")
            return DecisionOutput(
                decision=Decision.NO_TRADE,
                quality=TradeQuality.REJECTED,
                total_score=total_score,
                score_breakdown=weighted_scores,
                direction=None,
                confidence=Confidence.NONE,
                reasons=[],
                rejections=rejections,
                suggested_entry=None,
                suggested_sl=None,
                suggested_tp=None,
                risk_reward_ratio=None,
                generated_at=datetime.utcnow(),
                valid_until=None
            )

        # مرحله 4: تعیین کیفیت
        quality = self._determine_quality(total_score)

        # مرحله 5: تعیین اعتماد
        confidence = self._determine_confidence(weighted_scores, direction, inputs)

        # مرحله 6: جمع‌آوری دلایل
        reasons = self._collect_reasons(inputs, weighted_scores)

        # مرحله 7: محاسبه قیمت‌ها
        entry, sl, tp, rr = self._calculate_prices(inputs, direction)

        # تعیین تصمیم نهایی
        if quality == TradeQuality.REJECTED or quality == TradeQuality.WEAK:
            decision = Decision.NO_TRADE
        else:
            decision = Decision.BUY if direction == "bullish" else Decision.SELL

        output = DecisionOutput(
            decision=decision,
            quality=quality,
            total_score=total_score,
            score_breakdown=weighted_scores,
            direction=direction,
            confidence=confidence,
            reasons=reasons,
            rejections=[],
            suggested_entry=entry,
            suggested_sl=sl,
            suggested_tp=tp,
            risk_reward_ratio=rr,
            generated_at=datetime.utcnow(),
            valid_until=datetime.utcnow() + timedelta(hours=4)
        )

        # ذخیره
        self.recent_decisions.append(output)
        if len(self.recent_decisions) > 20:
            self.recent_decisions = self.recent_decisions[-20:]

        logger.info(f"تصمیم نهایی: {decision.value} | کیفیت: {quality.value} | امتیاز: {total_score:.2f}")

        return output

    def _calculate_weighted_scores(self, inputs: DecisionInput) -> Dict[str, float]:
        """
        محاسبه امتیاز وزنی هر بخش

        هر امتیاز در وزن مربوطه ضرب می‌شود.
        """
        return {
            "smc": inputs.smc_score * self.weights["smc"],
            "price_action": inputs.price_action_score * self.weights["price_action"],
            "liquidity": inputs.liquidity_score * self.weights["liquidity"],
            "mtf": inputs.mtf_score * self.weights["mtf"],
            "session": inputs.session_score * self.weights["session"],
            "volatility": inputs.volatility_score * self.weights["volatility"]
        }

    def _determine_direction(self, inputs: DecisionInput) -> Optional[str]:
        """
        تعیین جهت غالب

        برای ورود، حداقل {consensus}% بخش‌ها باید همجهت باشند.
        """
        directions = []
        weights_list = []

        # SMC
        if inputs.smc_direction in ("bullish", "bearish"):
            directions.append(inputs.smc_direction)
            weights_list.append(self.weights["smc"])

        # Price Action
        if inputs.price_action_direction in ("bullish", "bearish"):
            directions.append(inputs.price_action_direction)
            weights_list.append(self.weights["price_action"])

        # MTF
        if inputs.mtf_alignment.get("htf_bias") in ("bullish", "bearish"):
            directions.append(inputs.mtf_alignment["htf_bias"])
            weights_list.append(self.weights["mtf"])

        if not directions:
            return None

        # محاسبه وزن‌دار
        total_weight = sum(weights_list)
        bullish_weight = sum(w for d, w in zip(directions, weights_list) if d == "bullish")
        bearish_weight = sum(w for d, w in zip(directions, weights_list) if d == "bearish")

        bullish_ratio = bullish_weight / total_weight if total_weight > 0 else 0
        bearish_ratio = bearish_weight / total_weight if total_weight > 0 else 0

        if bullish_ratio >= self.direction_consensus:
            return "bullish"
        elif bearish_ratio >= self.direction_consensus:
            return "bearish"
        else:
            return None

    def _apply_filters(
        self,
        inputs: DecisionInput,
        direction: Optional[str],
        total_score: float
    ) -> Tuple[bool, List[str]]:
        """
        اعمال فیلترها

        Returns:
            (passed, rejections)
        """
        rejections = []

        # فیلتر 1: حداقل امتیاز
        if total_score < self.min_entry_score:
            rejections.append(
                f"امتیاز پایین ({total_score:.1f} < {self.min_entry_score})"
            )

        # فیلتر 2: وجود جهت
        if not direction:
            rejections.append("عدم توافق جهت")

        # فیلتر 3: ریسک
        if not inputs.risk_check_passed:
            rejections.append("ریسک مجاز نیست")

        # فیلتر 4: Kill Zone (در صورت فعال بودن)
        if inputs.session_details.get("require_killzone"):
            if not inputs.session_details.get("killzone_active"):
                rejections.append("خارج از Kill Zone")

        # فیلتر 5: نقدینگی کافی
        if inputs.liquidity_details.get("require_sweep"):
            if not inputs.liquidity_details.get("liquidity_swept"):
                rejections.append("نقدینگی اسویپ نشده")

        # فیلتر 6: MTF alignment
        if inputs.mtf_alignment.get("require_alignment"):
            if inputs.mtf_alignment.get("alignment") != direction:
                rejections.append("عدم همسویی MTF")

        return (len(rejections) == 0, rejections)

    def _determine_quality(self, total_score: float) -> TradeQuality:
        """تعیین کیفیت معامله"""
        if total_score >= self.excellent_threshold:
            return TradeQuality.EXCELLENT
        elif total_score >= self.good_threshold:
            return TradeQuality.GOOD
        elif total_score >= self.moderate_threshold:
            return TradeQuality.MODERATE
        elif total_score >= self.min_entry_score:
            return TradeQuality.WEAK
        else:
            return TradeQuality.REJECTED

    def _determine_confidence(
        self,
        weighted_scores: Dict[str, float],
        direction: Optional[str],
        inputs: DecisionInput
    ) -> Confidence:
        """تعیین سطح اعتماد"""
        if not direction:
            return Confidence.NONE

        # تعداد بخش‌های قوی
        strong_components = sum(1 for s in weighted_scores.values() if s > 5)

        if strong_components >= 4:
            return Confidence.VERY_HIGH
        elif strong_components >= 3:
            return Confidence.HIGH
        elif strong_components >= 2:
            return Confidence.MODERATE
        else:
            return Confidence.LOW

    def _collect_reasons(
        self,
        inputs: DecisionInput,
        weighted_scores: Dict[str, float]
    ) -> List[str]:
        """جمع‌آوری دلایل ورود"""
        reasons = []

        # SMC
        if weighted_scores["smc"] > 5:
            if inputs.smc_details.get("last_event"):
                event = inputs.smc_details["last_event"]
                reasons.append(f"{event.get('type', 'Structure')} {event.get('direction', '')}")

            if inputs.smc_details.get("liquidity_swept"):
                reasons.append("نقدینگی اسویپ شد")

            if inputs.smc_details.get("order_block_respected"):
                reasons.append("Order Block رعایت شد")

            if inputs.smc_details.get("premium_discount") == "discount":
                reasons.append("قیمت در تخفیف")

        # Price Action
        if weighted_scores["price_action"] > 5:
            patterns = inputs.price_action_details.get("patterns", [])
            for p in patterns[:2]:  # max 2
                reasons.append(f"الگوی {p.get('pattern_name', 'PA')}")

        # Session
        if weighted_scores["session"] > 3:
            if inputs.session_details.get("killzone_active"):
                reasons.append(f"Kill Zone {inputs.session_details.get('current_session', '')}")

        # MTF
        if weighted_scores["mtf"] > 3:
            reasons.append(f"توافق TF: {inputs.mtf_alignment.get('alignment', '')}")

        return reasons

    def _calculate_prices(
        self,
        inputs: DecisionInput,
        direction: Optional[str]
    ) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        محاسبه قیمت‌های پیشنهادی

        Returns:
            (entry, sl, tp, risk_reward)
        """
        if not direction or inputs.current_price == 0:
            return (None, None, None, None)

        # قیمت ورود: قیمت فعلی
        entry = inputs.current_price

        # استاپ لاس
        sl = inputs.smc_details.get("invalidation_level")
        if not sl:
            # محاسبه از swing
            if direction == "bullish":
                sl = inputs.smc_details.get("key_levels", {}).get("last_swing_low")
            else:
                sl = inputs.smc_details.get("key_levels", {}).get("last_swing_high")

        # تارگت: نقدینگی مخالف
        if direction == "bullish":
            tp_levels = inputs.liquidity_details.get("available_buy_side", [])
            tp = tp_levels[0] if tp_levels else None
        else:
            tp_levels = inputs.liquidity_details.get("available_sell_side", [])
            tp = tp_levels[0] if tp_levels else None

        # محاسبه R:R
        rr = None
        if entry and sl and tp:
            if direction == "bullish":
                risk = abs(entry - sl)
                reward = abs(tp - entry)
            else:
                risk = abs(sl - entry)
                reward = abs(entry - tp)

            if risk > 0:
                rr = round(reward / risk, 2)

        return (entry, sl, tp, rr)

    def get_statistics(self) -> Dict[str, Any]:
        """دریافت آمار تصمیم‌گیری"""
        if not self.recent_decisions:
            return {
                "total_decisions": 0,
                "buy_signals": 0,
                "sell_signals": 0,
                "no_trades": 0,
                "avg_score": 0
            }

        buy_count = sum(1 for d in self.recent_decisions if d.decision == Decision.BUY)
        sell_count = sum(1 for d in self.recent_decisions if d.decision == Decision.SELL)
        no_trade_count = sum(1 for d in self.recent_decisions if d.decision == Decision.NO_TRADE)
        avg_score = sum(d.total_score for d in self.recent_decisions) / len(self.recent_decisions)

        return {
            "total_decisions": len(self.recent_decisions),
            "buy_signals": buy_count,
            "sell_signals": sell_count,
            "no_trades": no_trade_count,
            "avg_score": round(avg_score, 2)
        }
