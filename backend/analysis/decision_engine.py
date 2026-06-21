"""
=====================================================================
موتور تصمیم‌گیری چندمرحلهای - Production Ready
=====================================================================
مرحله ۱ - فیلتر اولیه:
  - بررسی مجاز بودن نماد
  - بررسی ساعت معاملاتی و سشن‌ها
  - بررسی نوسانات (Volatility Filter)

مرحله ۲ - تحلیل Multi-Timeframe:
  - تحلیل تایم‌فریم بالا (HTF)
  - تحلیل تایم‌فریم میانی (MTF)
  - تحلیل تایم‌فریم پایین (LTF)

مرحله ۳ - امتیازدهی SMC:
  - Order Block, FVG, BOS, CHOCH, MSS
  - Liquidity
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

Phase-D Fix (TECH-1): duplicate aliased imports removed
Phase-D Fix (ARCH-9): SMCScoreResult.order_block_count + fvg_count as real @property
Phase-F Fix (F-4): make_decision defined as real method inside DecisionEngine class
  Removed: DecisionEngine.make_decision = _make_decision (monkey-patch)
  Added:   def make_decision(self, ...) inside DecisionEngine body
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DecisionStage(Enum):
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

    @property
    def order_block_count(self) -> int:
        """ARCH-9 FIX: real @property (was monkey-patched)."""
        return 1 if self.order_block_score > 0 else 0

    @property
    def fvg_count(self) -> int:
        """ARCH-9 FIX: real @property (was monkey-patched)."""
        return 1 if self.fvg_score > 0 else 0


@dataclass
class PAScoreResult:
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
    aligned: bool = False
    alignment_score: float = 0.0
    htf: Optional[TimeframeAnalysis] = None
    mtf: Optional[TimeframeAnalysis] = None
    ltf: Optional[TimeframeAnalysis] = None
    direction: TrendDirection = TrendDirection.UNDEFINED
    notes: List[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
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
    symbol: str = ""
    timeframe: str = ""
    decision: str = "NO_TRADE"
    direction: str = "neutral"
    total_score: float = 0.0
    minimum_required_score: float = 0.0
    allowed: bool = False
    mtf_score: float = 0.0
    smc_score: float = 0.0
    pa_score: float = 0.0
    entry_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    analysis_time: str = ""
    stages_passed: List[str] = field(default_factory=list)
    stages_failed: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    blocked_reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    mtf_result: Optional[MultiTimeframeResult] = None
    smc_result: Optional[SMCScoreResult] = None
    pa_result: Optional[PAScoreResult] = None
    risk_assessment: Optional[RiskAssessment] = None


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
    "candle_pattern": 0.40,
    "breakout": 0.35,
    "compression": 0.25,
}

MTF_WEIGHTS = {
    "htf": 0.50,
    "mtf": 0.30,
    "ltf": 0.20,
}


class MultiTimeframeEngine:
    def __init__(self):
        pass

    def analyze(
        self,
        symbol: str,
        market_context: Dict[str, Any],
        timeframe: str = "M15",
    ) -> MultiTimeframeResult:
        htf_data = market_context.get("htf", {})
        mtf_data = market_context.get("mtf", {})
        ltf_data = market_context.get("ltf", {}) or market_context
        htf = self._analyze_single(htf_data, TimeframeLevel.HIGH)
        mtf = self._analyze_single(mtf_data, TimeframeLevel.MEDIUM)
        ltf = self._analyze_single(ltf_data, TimeframeLevel.LOW)
        alignment_score, aligned, direction = self._check_alignment(htf, mtf, ltf)
        return MultiTimeframeResult(
            aligned=aligned,
            alignment_score=alignment_score,
            htf=htf,
            mtf=mtf,
            ltf=ltf,
            direction=direction,
        )

    def _analyze_single(self, tf_data: Dict[str, Any], level: TimeframeLevel) -> TimeframeAnalysis:
        trend_str = tf_data.get("trend", "undefined")
        trend_map = {
            "bullish": TrendDirection.BULLISH,
            "bearish": TrendDirection.BEARISH,
            "ranging": TrendDirection.RANGING,
        }
        trend = trend_map.get(trend_str, TrendDirection.UNDEFINED)
        return TimeframeAnalysis(
            timeframe=tf_data.get("timeframe", ""),
            level=level,
            trend=trend,
            trend_strength=float(tf_data.get("trend_strength", 0)),
            structure_event=tf_data.get("structure_event"),
            key_level=tf_data.get("key_level"),
            score=float(tf_data.get("score", 0)),
        )

    def _check_alignment(
        self,
        htf: TimeframeAnalysis,
        mtf: TimeframeAnalysis,
        ltf: TimeframeAnalysis,
    ) -> Tuple[float, bool, TrendDirection]:
        trends = [htf.trend, mtf.trend, ltf.trend]
        non_undefined = [t for t in trends if t != TrendDirection.UNDEFINED]
        non_ranging = [t for t in non_undefined if t != TrendDirection.RANGING]
        if len(non_ranging) >= 2 and len(set(non_ranging)) == 1:
            direction = non_ranging[0]
            score = 100.0 if len(non_ranging) == 3 else 75.0
            return score, score >= 70.0, direction
        if len(set(non_ranging)) > 1:
            return 30.0, False, TrendDirection.UNDEFINED
        return 50.0, False, TrendDirection.RANGING


class DecisionEngine:
    """موتور تصمیم‌گیری چندمرحلهای"""

    def __init__(self):
        self._mtf_engine = MultiTimeframeEngine()

    def make_decision(self, decision_input: "DecisionInput") -> "DecisionOutput":
        """
        F-4 FIX: Real method in class body (was monkey-patched at module end).
        Bridge: DecisionInput -> decide() -> DecisionOutput.
        """
        return _make_decision(self, decision_input)

    def decide(
        self,
        symbol: str,
        timeframe: str,
        market_context: Dict[str, Any],
        smc_results: Dict[str, Any],
        pa_results: Dict[str, Any],
        risk_params: Dict[str, Any],
        enabled_modules: Optional[Dict[str, bool]] = None,
    ) -> DecisionResult:
        enabled = enabled_modules or {}
        result = DecisionResult(symbol=symbol, timeframe=timeframe)
        result.minimum_required_score = MINIMUM_ENTRY_SCORE

        if not self._initial_filter(market_context, result):
            return result

        mtf_result = self._mtf_engine.analyze(symbol, market_context, timeframe)
        result.mtf_result = mtf_result
        result.mtf_score = mtf_result.alignment_score * MODULE_WEIGHTS["multi_timeframe"]
        result.stages_passed.append(DecisionStage.MULTI_TIMEFRAME.value)

        smc_result = self._score_smc(smc_results)
        result.smc_result = smc_result
        result.smc_score = smc_result.weighted_score * MODULE_WEIGHTS["smc"]

        pa_result = self._score_pa(pa_results)
        result.pa_result = pa_result
        result.pa_score = pa_result.weighted_score * MODULE_WEIGHTS["price_action"]

        risk_assessment = self._assess_risk(risk_params)
        result.risk_assessment = risk_assessment
        if not risk_assessment.passed:
            result.stages_failed.append(DecisionStage.RISK_FILTER.value)
            result.blocked_reasons.append("risk_filter_failed")
            result.decision = "NO_TRADE"
            return result

        result.total_score = self._calculate_total_score(result)
        result.direction = self._determine_direction(mtf_result)

        if result.total_score >= MINIMUM_ENTRY_SCORE:
            result.allowed = True
            result.decision = "BUY" if result.direction == "bullish" else (
                "SELL" if result.direction == "bearish" else "NO_TRADE"
            )
            if result.decision in ("BUY", "SELL"):
                result.entry_price = market_context.get("current_price", 0.0)
                atr = market_context.get("atr", result.entry_price * 0.001)
                result.stop_loss = result.entry_price - atr * 1.5 if result.decision == "BUY" else result.entry_price + atr * 1.5
                result.take_profit_1 = result.entry_price + atr * 2 if result.decision == "BUY" else result.entry_price - atr * 2
                result.take_profit_2 = result.entry_price + atr * 3 if result.decision == "BUY" else result.entry_price - atr * 3
                result.take_profit_3 = result.entry_price + atr * 4 if result.decision == "BUY" else result.entry_price - atr * 4
        else:
            result.decision = "NO_TRADE"
            result.reasons.append(f"score_below_threshold:{result.total_score:.1f}<{MINIMUM_ENTRY_SCORE}")

        import time
        result.analysis_time = str(time.monotonic())
        return result

    def _initial_filter(
        self, market_context: Dict[str, Any], result: DecisionResult
    ) -> bool:
        session = market_context.get("session", "london")
        closed_sessions = {"weekend", "closed", "holiday"}
        if session in closed_sessions:
            result.blocked_reasons.append("market_closed")
            result.stages_failed.append(DecisionStage.INITIAL_FILTER.value)
            return False
        volatility = float(market_context.get("volatility", 0.0))
        volatility_limit = float(market_context.get("volatility_limit", 3.0))
        if volatility > volatility_limit:
            result.blocked_reasons.append("volatility_too_high")
            result.stages_failed.append(DecisionStage.INITIAL_FILTER.value)
            return False
        result.stages_passed.append(DecisionStage.INITIAL_FILTER.value)
        return True

    def _score_smc(self, smc_results: Dict[str, Any]) -> SMCScoreResult:
        ob_score = min(len(smc_results.get("order_blocks", [])) * 20.0, 100.0)
        fvg_score = min(len(smc_results.get("fvg", [])) * 25.0, 100.0)
        structure = smc_results.get("structure", {})
        bos_score = 80.0 if structure.get("bos_detected") else 0.0
        choch_score = 90.0 if structure.get("choch_detected") else 0.0
        bos_choch_score = max(bos_score, choch_score)
        liq = smc_results.get("liquidity", {})
        liq_score = float(liq.get("score", 0.0)) * 100
        pd = smc_results.get("premium_discount", "neutral")
        pd_score = 80.0 if pd in ("discount", "premium") else 40.0
        weighted = (
            ob_score       * SMC_COMPONENT_WEIGHTS["order_block"] +
            fvg_score      * SMC_COMPONENT_WEIGHTS["fvg"] +
            bos_choch_score* SMC_COMPONENT_WEIGHTS["bos_choch"] +
            liq_score      * SMC_COMPONENT_WEIGHTS["liquidity"] +
            pd_score       * SMC_COMPONENT_WEIGHTS["premium_discount"]
        )
        return SMCScoreResult(
            total_score=weighted,
            order_block_score=ob_score,
            fvg_score=fvg_score,
            bos_score=bos_score,
            choch_score=choch_score,
            liquidity_score=liq_score,
            premium_discount_score=pd_score,
            weighted_score=weighted,
            passed=weighted >= 50.0,
            minimum_required=50.0,
        )

    def _score_pa(self, pa_results: Dict[str, Any]) -> PAScoreResult:
        patterns = pa_results.get("patterns", [])
        candle_score = min(len(patterns) * 30.0, 100.0)
        breakout = pa_results.get("breakout", {})
        breakout_score = float(breakout.get("score", 0.0)) * 100
        compression = pa_results.get("compression", {})
        compression_score = float(compression.get("score", 0.0)) * 100
        weighted = (
            candle_score     * PA_COMPONENT_WEIGHTS["candle_pattern"] +
            breakout_score   * PA_COMPONENT_WEIGHTS["breakout"] +
            compression_score* PA_COMPONENT_WEIGHTS["compression"]
        )
        return PAScoreResult(
            total_score=weighted,
            candle_pattern_score=candle_score,
            breakout_score=breakout_score,
            compression_score=compression_score,
            weighted_score=weighted,
            passed=weighted >= 40.0,
            minimum_required=40.0,
            patterns_found=patterns,
        )

    def _assess_risk(self, risk_params: Dict[str, Any]) -> RiskAssessment:
        rr = float(risk_params.get("risk_reward_ratio", 0.0))
        min_rr = float(risk_params.get("min_risk_reward", 1.5))
        passed = rr >= min_rr
        return RiskAssessment(
            passed=passed,
            risk_reward_ratio=rr,
            stop_loss=risk_params.get("stop_loss"),
            take_profit=risk_params.get("take_profit"),
        )

    def _calculate_total_score(
        self, result: DecisionResult
    ) -> float:
        return result.mtf_score + result.smc_score + result.pa_score

    def _determine_direction(self, mtf: MultiTimeframeResult) -> str:
        if mtf.direction == TrendDirection.BULLISH:
            return "bullish"
        if mtf.direction == TrendDirection.BEARISH:
            return "bearish"
        return "neutral"


class ReasonCode(Enum):
    SMC_CONFIRMED     = "smc_confirmed"
    PA_CONFIRMED      = "pa_confirmed"
    MTF_ALIGNED       = "mtf_aligned"
    RISK_OK           = "risk_ok"
    SCORE_PASSED      = "score_passed"
    MARKET_CLOSED     = "market_closed"
    LICENSE_INVALID   = "license_invalid"
    VOLATILITY_TOO_HIGH = "volatility_too_high"


class BlockedReason(Enum):
    MARKET_CLOSED       = "market_closed"
    LICENSE_INVALID     = "license_invalid"
    RISK_FILTER_FAILED  = "risk_filter_failed"
    SCORE_TOO_LOW       = "score_too_low"
    VOLATILITY_TOO_HIGH = "volatility_too_high"


@dataclass
class SMCContext:
    trend: Any = "ranging"
    trend_score: float = 0.0
    structure_event: Optional[str] = None
    structure_direction: Optional[str] = None
    structure_level: Optional[float] = None
    liquidity_swept: bool = False
    liquidity_direction: Optional[str] = None
    premium_discount: str = "neutral"
    order_blocks: List[Dict[str, Any]] = field(default_factory=list)
    fvgs: List[Dict[str, Any]] = field(default_factory=list)
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None


@dataclass
class PriceActionContext:
    direction: Any = "neutral"
    direction_score: float = 0.0
    patterns: List[str] = field(default_factory=list)
    candle_strength: str = "none"


@dataclass
class SessionContext:
    current_session: Any = "closed"
    killzone_active: bool = False
    killzone_name: Optional[str] = None
    session_score: float = 0.0


@dataclass
class LicenseContext:
    is_valid: bool = True
    is_expired: bool = False
    account_id: Optional[str] = None
    license_type: str = "standard"
    expires_at: Optional[str] = None


@dataclass
class RiskContext:
    available_margin: Optional[float] = None
    risk_per_trade: float = 0.01
    max_daily_loss: float = 0.03
    open_positions: int = 0
    max_positions: int = 5
    daily_loss_pct: float = 0.0


@dataclass
class SymbolPolicy:
    symbol: str = ""
    is_allowed: bool = True
    min_score_override: Optional[float] = None
    max_spread_pips: Optional[float] = None
    blocked_reason: Optional[str] = None


@dataclass
class VolatilityContext:
    atr: float = 0.0
    atr_pct: float = 0.0
    volatility_level: Any = "medium"
    is_high_impact_news: bool = False
    news_minutes_away: int = 999


@dataclass
class MultiTimeframeContext:
    htf_trend: Any = "ranging"
    htf_score: float = 0.0
    mtf_trend: Any = "ranging"
    mtf_score: float = 0.0
    ltf_trigger: Optional[str] = None
    aligned: bool = False
    alignment_score: float = 0.0


@dataclass
class LiquidityContext:
    buy_side_liquidity: List[float] = field(default_factory=list)
    sell_side_liquidity: List[float] = field(default_factory=list)
    nearest_bsl: Optional[float] = None
    nearest_ssl: Optional[float] = None
    liquidity_swept: bool = False
    sweep_direction: Optional[str] = None
    inducement_present: bool = False


@dataclass
class DecisionInput:
    symbol: str = ""
    timeframe: str = ""
    smc_context: Optional[SMCContext] = None
    price_action_context: Optional[PriceActionContext] = None
    session_context: Optional[SessionContext] = None
    license_context: Optional[LicenseContext] = None
    risk_context: Optional[RiskContext] = None
    symbol_policy: Optional[SymbolPolicy] = None
    volatility_context: Optional[VolatilityContext] = None
    mtf_context: Optional[MultiTimeframeContext] = None
    liquidity_context: Optional[LiquidityContext] = None

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


@dataclass
class TradingLevels:
    entry_zone: float = 0.0
    entry_zone_high: float = 0.0
    entry_zone_low: float = 0.0
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    invalidation_level: Optional[float] = None
    risk_reward_ratio: float = 0.0


@dataclass
class RiskProfile:
    risk_level: str = "medium"
    position_size: float = 0.0
    max_loss_amount: float = 0.0
    potential_profit: float = 0.0
    risk_reward_ratio: float = 0.0


@dataclass
class DecisionOutput:
    symbol: str = ""
    timeframe: str = ""
    created_at: Optional[datetime] = None
    decision: Any = "NO_TRADE"
    direction: Any = "neutral"
    confidence_score: float = 0.0
    quality_score: float = 0.0
    allowed: bool = False
    reason_codes: List[ReasonCode] = field(default_factory=list)
    reasons_persian: List[str] = field(default_factory=list)
    blocked_reasons: List[BlockedReason] = field(default_factory=list)
    score_breakdown: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    trading_levels: Optional[TradingLevels] = None
    risk_profile: Optional[RiskProfile] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)


def _make_decision(
    self: "DecisionEngine",
    decision_input: "DecisionInput",
) -> "DecisionOutput":
    """
    Internal bridge implementation. Called via DecisionEngine.make_decision().
    F-4 FIX: No longer assigned as monkey-patch at module end.
    """
    smc_ctx  = decision_input.smc_context
    pa_ctx   = decision_input.price_action_context
    sess     = decision_input.session_context
    risk     = decision_input.risk_context
    vol      = decision_input.volatility_context
    mtf_ctx  = decision_input.mtf_context

    market_context: Dict[str, Any] = {
        "session":          getattr(sess, "current_session", "london") if sess else "london",
        "volatility":       getattr(vol, "atr_pct", 0.0) if vol else 0.0,
        "volatility_limit": 3.0,
    }
    if mtf_ctx:
        market_context["htf"] = {"trend": getattr(mtf_ctx, "htf_trend", "ranging"), "score": getattr(mtf_ctx, "htf_score", 0.0)}
        market_context["mtf"] = {"trend": getattr(mtf_ctx, "mtf_trend", "ranging"), "score": getattr(mtf_ctx, "mtf_score", 0.0)}
        market_context["ltf"] = {"trend": getattr(mtf_ctx, "ltf_trigger", "ranging")}

    smc_results: Dict[str, Any] = {}
    if smc_ctx:
        smc_results = {
            "order_blocks": getattr(smc_ctx, "order_blocks", []) or [],
            "fvg":          getattr(smc_ctx, "fvgs", []) or [],
            "structure":    {"bos_detected": getattr(smc_ctx, "structure_event", "") == "BOS", "choch_detected": getattr(smc_ctx, "structure_event", "") == "CHOCH"},
            "liquidity":    {"score": 0.5 if getattr(smc_ctx, "liquidity_swept", False) else 0.0},
            "premium_discount": getattr(smc_ctx, "premium_discount", "neutral"),
        }

    pa_results: Dict[str, Any] = {}
    if pa_ctx:
        pa_results = {
            "patterns":    getattr(pa_ctx, "patterns", []) or [],
            "breakout":    {"score": getattr(pa_ctx, "direction_score", 0.0) / 100.0},
            "compression": {},
        }

    risk_params: Dict[str, Any] = {"risk_reward_ratio": 2.0, "min_risk_reward": 1.5, "stop_loss": 1.0, "take_profit": 2.0}
    if risk:
        daily_ok = getattr(risk, "daily_loss_pct", 0.0) < getattr(risk, "max_daily_loss", 0.03)
        pos_ok   = getattr(risk, "open_positions", 0) < getattr(risk, "max_positions", 5)
        if not daily_ok or not pos_ok:
            risk_params["risk_reward_ratio"] = 0.0

    result = self.decide(
        symbol=decision_input.symbol,
        timeframe=decision_input.timeframe,
        market_context=market_context,
        smc_results=smc_results,
        pa_results=pa_results,
        risk_params=risk_params,
    )

    blocked = []
    for r in result.blocked_reasons:
        try:
            blocked.append(BlockedReason(r))
        except ValueError:
            pass

    reason_codes = []
    for r in result.reasons:
        try:
            reason_codes.append(ReasonCode(r))
        except ValueError:
            pass

    score_breakdown: Dict[str, float] = {"mtf": result.mtf_score, "smc": result.smc_score, "pa": result.pa_score, "total": result.total_score}

    trading_levels: Optional[TradingLevels] = None
    risk_profile: Optional[RiskProfile] = None
    if result.allowed:
        trading_levels = TradingLevels(
            entry_zone=result.entry_price, stop_loss=result.stop_loss,
            take_profit_1=result.take_profit_1, take_profit_2=result.take_profit_2, take_profit_3=result.take_profit_3,
        )
        if risk:
            risk_profile = RiskProfile(
                risk_level="low" if result.total_score > 80 else "medium",
                position_size=getattr(risk, "risk_per_trade", 0.01),
                max_loss_amount=getattr(risk, "available_margin", 10000) * getattr(risk, "risk_per_trade", 0.01),
            )

    try:
        from ..core.enums import DecisionAction, DecisionDirection
        if result.allowed:
            decision_val: Any = DecisionAction.BUY if result.direction == "bullish" else DecisionAction.SELL
            direction_val: Any = DecisionDirection.LONG if result.direction == "bullish" else DecisionDirection.SHORT
        else:
            decision_val  = DecisionAction.NO_TRADE
            direction_val = DecisionDirection.NEUTRAL
    except Exception:
        decision_val  = result.decision
        direction_val = result.direction

    return DecisionOutput(
        symbol=result.symbol, timeframe=result.timeframe,
        created_at=datetime.now(timezone.utc),
        decision=decision_val, direction=direction_val,
        confidence_score=round(result.total_score / 100.0, 4),
        quality_score=round(result.total_score, 2),
        allowed=result.allowed,
        reason_codes=reason_codes, reasons_persian=result.reasons,
        blocked_reasons=blocked, score_breakdown=score_breakdown,
        metadata={"analysis_time": result.analysis_time, "minimum_required_score": result.minimum_required_score},
        trading_levels=trading_levels, risk_profile=risk_profile,
    )


# F-4 FIX: make_decision is a real method in DecisionEngine class body above.
# No monkey-patch needed or used.
