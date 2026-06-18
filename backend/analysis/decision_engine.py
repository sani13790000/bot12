"""
=====================================================================
ÙÙØªÙØ± ØªØµÙÛÙâÚ¯ÛØ±Û ÚÙØ¯ÙØ±Ø­ÙÙâØ§Û - Production Ready
=====================================================================
Ø§ÛÙ ÙÙØªÙØ± Ø¨Ø§ ÙØ¹ÙØ§Ø±Û ÚÙØ¯ÙØ±Ø­ÙÙâØ§Û (Stage-based) ØªØµÙÛÙ ÙØ¹Ø§ÙÙØ§ØªÛ ÙÛâÚ¯ÛØ±Ø¯:

ÙØ±Ø­ÙÙ Û± - ÙÛÙØªØ± Ø§ÙÙÛÙ:
  - Ø¨Ø±Ø±Ø³Û ÙØ¬Ø§Ø² Ø¨ÙØ¯Ù ÙÙØ§Ø¯
  - Ø¨Ø±Ø±Ø³Û Ø³Ø§Ø¹Øª ÙØ¹Ø§ÙÙØ§ØªÛ Ù Ø³Ø´ÙâÙØ§
  - Ø¨Ø±Ø±Ø³Û ÙÙØ³Ø§ÙØ§Øª (Volatility Filter)

ÙØ±Ø­ÙÙ Û² - ØªØ­ÙÛÙ Multi-Timeframe:
  - ØªØ­ÙÛÙ ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§ (HTF): Ø±ÙÙØ¯ Ú©ÙÛ
  - ØªØ­ÙÛÙ ØªØ§ÛÙâÙØ±ÛÙ ÙÛØ§ÙÛ (MTF): Ø³Ø§Ø®ØªØ§Ø± Ù ÙØ§Ø­ÛÙ
  - ØªØ­ÙÛÙ ØªØ§ÛÙâÙØ±ÛÙ Ù¾Ø§ÛÛÙ (LTF): ØªØ±ÛÚ¯Ø± ÙØ±ÙØ¯

ÙØ±Ø­ÙÙ Û³ - Ø§ÙØªÛØ§Ø²Ø¯ÙÛ SMC:
  - Order BlockØ FVGØ BOSØ CHOCHØ MSS
  - Liquidity (Ø¯Ø§Ø®ÙÛ Ù Ø®Ø§Ø±Ø¬Û)
  - Premium/Discount Zone

ÙØ±Ø­ÙÙ Û´ - Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Price Action:
  - Ø§ÙÚ¯ÙÙØ§Û Ø´ÙØ¹Û
  - Breakout Ù Retest
  - Compression/Expansion

ÙØ±Ø­ÙÙ Ûµ - ÙÛÙØªØ± Ø±ÛØ³Ú©:
  - ÙØ³Ø¨Øª Ø±ÛØ³Ú© Ø¨Ù Ø±ÛÙØ§Ø±Ø¯
  - Ø­Ø¯Ø§Ú©Ø«Ø± Ø¶Ø±Ø± Ø±ÙØ²Ø§ÙÙ
  - ØªØ¹Ø¯Ø§Ø¯ ÙØ¹Ø§ÙÙØ§Øª ÙÙØ²ÙØ§Ù

ÙØ±Ø­ÙÙ Û¶ - ØªØµÙÛÙ ÙÙØ§ÛÛ:
  - Ø¬ÙØ¹ Ø§ÙØªÛØ§Ø²Ø§Øª ÙØ²ÙâØ¯ÙÛ Ø´Ø¯Ù
  - ÙÙØ§ÛØ³Ù Ø¨Ø§ Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² ÙØ¬Ø§Ø²
  - Ø®Ø±ÙØ¬Û: BUY / SELL / NO_TRADE

ÙÙÛØ³ÙØ¯Ù: MT5 Trading Team
ÙØ³Ø®Ù: 3.0.0
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class DecisionStage(Enum):
    """ÙØ±Ø§Ø­Ù ØªØµÙÛÙâÚ¯ÛØ±Û"""
    INITIAL_FILTER = "initial_filter"
    MULTI_TIMEFRAME = "multi_timeframe"
    SMC_SCORING = "smc_scoring"
    PRICE_ACTION_SCORING = "price_action_scoring"
    RISK_FILTER = "risk_filter"
    FINAL_DECISION = "final_decision"


class TimeframeLevel(Enum):
    """Ø³Ø·ÙØ­ ØªØ§ÛÙâÙØ±ÛÙ"""
    HTF = "htf"   # ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§ - Ø±ÙÙØ¯ Ú©ÙÛ
    MTF = "mtf"   # ØªØ§ÛÙâÙØ±ÛÙ ÙÛØ§ÙÛ - ÙØ§Ø­ÛÙ Ù Ø³Ø§Ø®ØªØ§Ø±
    LTF = "ltf"   # ØªØ§ÛÙâÙØ±ÛÙ Ù¾Ø§ÛÛÙ - ØªØ±ÛÚ¯Ø± ÙØ±ÙØ¯


class TrendDirection(Enum):
    """Ø¬ÙØª Ø±ÙÙØ¯"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGING = "ranging"
    UNKNOWN = "unknown"


@dataclass
class TimeframeAnalysis:
    """
    ÙØªÛØ¬Ù ØªØ­ÙÛÙ ÛÚ© ØªØ§ÛÙâÙØ±ÛÙ

    Ø´Ø§ÙÙ Ø±ÙÙØ¯Ø Ø³Ø§Ø®ØªØ§Ø±Ø ÙØ§Ø­ÛÙâÙØ§Û Ú©ÙÛØ¯Û Ù Ø§ÙØªÛØ§Ø²
    """
    timeframe: str
    level: TimeframeLevel
    trend: TrendDirection
    structure_score: float        # Ø§ÙØªÛØ§Ø² Ø³Ø§Ø®ØªØ§Ø± Ø¨Ø§Ø²Ø§Ø± (0-100)
    in_key_zone: bool             # Ø¢ÛØ§ Ø¯Ø± ÙØ§Ø­ÛÙ Ú©ÙÛØ¯Û Ø§Ø³ØªØ
    zone_type: str                # ÙÙØ¹ ÙØ§Ø­ÛÙ (OB, FVG, ...)
    zone_score: float             # Ø§ÙØªÛØ§Ø² Ú©ÛÙÛØª ÙØ§Ø­ÛÙ (0-100)
    momentum_score: float         # Ø§ÙØªÛØ§Ø² ÙÙÙÙØªÙÙ (0-100)
    aligned_with_htf: bool        # ÙÙØ³Ù Ø¨Ø§ ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§
    confluence_count: int         # ØªØ¹Ø¯Ø§Ø¯ Ø¹ÙØ§ÙÙ ÙÙÚ¯Ø±Ø§
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SMCScoreResult:
    """
    ÙØªÛØ¬Ù Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Smart Money Concept

    ÙØ± ÙÙÙÙÙ SMC Ø§ÙØªÛØ§Ø² Ø¬Ø¯Ø§Ú¯Ø§ÙÙ Ø¯Ø§Ø±Ø¯ Ù Ø¯Ø± ÙÙØ§ÛØª ÙØ²ÙâØ¯ÙÛ ÙÛâØ´ÙØ¯.
    """
    # Ø³Ø§Ø®ØªØ§Ø± Ø¨Ø§Ø²Ø§Ø±
    market_structure_score: float = 0.0    # BOSØ CHOCHØ MSS
    bos_confirmed: bool = False
    choch_confirmed: bool = False
    mss_confirmed: bool = False

    # ÙØ§Ø­ÛÙâÙØ§Û ÙØ¹Ø§ÙÙØ§ØªÛ
    order_block_score: float = 0.0         # Order Block Ú©ÛÙÛØª
    mitigation_block_score: float = 0.0   # Mitigation Block
    breaker_block_score: float = 0.0      # Breaker Block
    rejection_block_score: float = 0.0    # Rejection Block

    # Ø´Ú©Ø§ÙâÙØ§Û ÙÛÙØªÛ
    fvg_score: float = 0.0                # Fair Value Gap
    ifvg_score: float = 0.0              # Inverse FVG

    # ÙÙØ¯ÛÙÚ¯Û
    internal_liquidity_score: float = 0.0
    external_liquidity_score: float = 0.0
    liquidity_sweep_confirmed: bool = False

    # ÙØ§Ø­ÛÙ ÙÛÙØªÛ
    premium_discount_score: float = 0.0   # Ø¢ÛØ§ Ø¯Ø± discount/premium Ø§Ø³ØªØ
    equilibrium_score: float = 0.0        # ÙØ§ØµÙÙ Ø§Ø² ØªØ¹Ø§Ø¯Ù

    # Ø³Ø´Ù
    kill_zone_active: bool = False
    session_liquidity_score: float = 0.0

    # Ø§ÙØªÛØ§Ø² Ú©ÙÛ SMC
    total_score: float = 0.0
    confidence: float = 0.0


@dataclass
class PAScoreResult:
    """
    ÙØªÛØ¬Ù Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Price Action

    ÙØ± Ø§ÙÚ¯Ù Ø§ÙØªÛØ§Ø² Ø¬Ø¯Ø§Ú¯Ø§ÙÙ Ø¯Ø§Ø±Ø¯ Ø¨Ø± Ø§Ø³Ø§Ø³ Ú©ÛÙÛØª Ù ÙÙÙØ¹ÛØª Ø¢Ù.
    """
    # Ø§ÙÚ¯ÙÙØ§Û Ø´ÙØ¹Û ØªÚ© Ø´ÙØ¹Û
    pin_bar_score: float = 0.0
    doji_score: float = 0.0

    # Ø§ÙÚ¯ÙÙØ§Û Ø¯Ù Ø´ÙØ¹Û
    engulfing_score: float = 0.0
    inside_bar_score: float = 0.0
    outside_bar_score: float = 0.0

    # Ø§ÙÚ¯ÙÙØ§Û Ù¾ÛÚÛØ¯Ù
    fakey_score: float = 0.0
    morning_star_score: float = 0.0
    evening_star_score: float = 0.0
    three_soldiers_score: float = 0.0
    three_crows_score: float = 0.0

    # Ø§ÙÚ¯ÙÙØ§Û Ø³Ø§Ø®ØªØ§Ø±Û
    breakout_score: float = 0.0
    retest_score: float = 0.0
    compression_score: float = 0.0
    expansion_score: float = 0.0

    # Ø¬ÙØª Ø³ÛÚ¯ÙØ§Ù Ø§Ø² PA
    bullish_signals: int = 0
    bearish_signals: int = 0

    # Ø§ÙØªÛØ§Ø² Ú©ÙÛ PA
    total_score: float = 0.0
    dominant_direction: str = "neutral"


@dataclass
class MultiTimeframeResult:
    """
    ÙØªÛØ¬Ù ØªØ­ÙÛÙ Multi-Timeframe

    ØªØ­ÙÛÙ Ø³Ù Ø³Ø·Ø­ ØªØ§ÛÙâÙØ±ÛÙ Ù ÙÙØ³ÙÛÛ Ø¨ÛÙ Ø¢ÙâÙØ§
    """
    htf: TimeframeAnalysis          # ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§
    mtf: TimeframeAnalysis          # ØªØ§ÛÙâÙØ±ÛÙ ÙÛØ§ÙÛ
    ltf: TimeframeAnalysis          # ØªØ§ÛÙâÙØ±ÛÙ Ù¾Ø§ÛÛÙ

    # ÙÙØ³ÙÛÛ
    all_aligned: bool = False        # ÙØ± Ø³Ù ÙÙØ³Ù ÙØ³ØªÙØ¯Ø
    htf_mtf_aligned: bool = False   # HTF Ù MTF ÙÙØ³Ù
    mtf_ltf_aligned: bool = False   # MTF Ù LTF ÙÙØ³Ù

    # Ø¬ÙØª Ú©ÙÛ
    overall_direction: TrendDirection = TrendDirection.UNKNOWN

    # Ø§ÙØªÛØ§Ø² ÙÙØ³ÙÛÛ (0-100)
    alignment_score: float = 0.0

    # Ø§ÙØªÛØ§Ø² Ú©ÙÛ MTF
    total_score: float = 0.0


@dataclass
class RiskAssessment:
    """
    Ø§Ø±Ø²ÛØ§Ø¨Û Ø±ÛØ³Ú© ÙØ¹Ø§ÙÙÙ

    ØªÙØ§Ù Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§Û Ø±ÛØ³Ú© Ø¨Ø±Ø±Ø³Û ÙÛâØ´ÙØ¯.
    """
    # ÙØ³Ø¨ØªâÙØ§
    risk_reward_ratio: float = 0.0     # ÙØ³Ø¨Øª Ø±ÛØ³Ú© Ø¨Ù Ø±ÛÙØ§Ø±Ø¯
    risk_percent: float = 0.0          # Ø¯Ø±ØµØ¯ Ø±ÛØ³Ú© Ø§Ø² ÙÙØ¬ÙØ¯Û

    # ÙÛÙØªØ±ÙØ§
    rr_pass: bool = False              # RR Ø­Ø¯Ø§ÙÙ 1:1.5 Ø¨Ø§Ø´Ø¯
    daily_loss_pass: bool = False      # Ø­Ø¯Ø§Ú©Ø«Ø± Ø¶Ø±Ø± Ø±ÙØ²Ø§ÙÙ Ø±Ø¯ ÙØ´Ø¯Ù
    max_trades_pass: bool = False      # ØªØ¹Ø¯Ø§Ø¯ ÙØ¹Ø§ÙÙØ§Øª ÙÙØ²ÙØ§Ù ÙØ¬Ø§Ø²
    volatility_pass: bool = False      # ÙÙØ³Ø§ÙØ§Øª Ø¯Ø± ÙØ­Ø¯ÙØ¯Ù ÙØ¬Ø§Ø²
    spread_pass: bool = False          # Ø§Ø³Ù¾Ø±Ø¯ Ø¯Ø± Ø­Ø¯ ÙØ¬Ø§Ø²

    # Ø§ÙØªÛØ§Ø² Ø±ÛØ³Ú© (ÙØ± ÚÙ Ø¨Ø§ÙØ§ØªØ± Ø¨ÙØªØ±)
    risk_score: float = 0.0

    # Ø¯ÙØ§ÛÙ Ø±Ø¯
    rejection_reasons: List[str] = field(default_factory=list)


@dataclass
class DecisionResult:
    """
    ÙØªÛØ¬Ù ÙÙØ§ÛÛ ÙÙØªÙØ± ØªØµÙÛÙâÚ¯ÛØ±Û

    Ø´Ø§ÙÙ ØªØµÙÛÙØ Ø§ÙØªÛØ§Ø² Ú©Ø§ÙÙØ Ù ØªÙØ§Ù Ø¬Ø²Ø¦ÛØ§Øª Ø¨Ø±Ø§Û ÙØ§Ú¯ Ù Ø¯Ø§Ø´Ø¨ÙØ±Ø¯
    """
    # ØªØµÙÛÙ Ø§ØµÙÛ
    decision: str = "NO_TRADE"         # BUY / SELL / NO_TRADE

    # Ø§ÙØªÛØ§Ø²Ø§Øª ÙØ± ÙØ±Ø­ÙÙ
    mtf_score: float = 0.0
    smc_score: float = 0.0
    pa_score: float = 0.0
    risk_score: float = 0.0
    session_score: float = 0.0

    # Ø§ÙØªÛØ§Ø² Ú©ÙÛ ÙÙØ§ÛÛ
    total_score: float = 0.0
    minimum_required_score: float = 65.0

    # Ø§Ø·ÙØ§Ø¹Ø§Øª ÙØ±ÙØ¯
    suggested_direction: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0

    # Ø¬Ø²Ø¦ÛØ§Øª ØªØ­ÙÛÙ
    mtf_result: Optional[MultiTimeframeResult] = None
    smc_result: Optional[SMCScoreResult] = None
    pa_result: Optional[PAScoreResult] = None
    risk_assessment: Optional[RiskAssessment] = None

    # ÙØ§Ú¯
    stage_log: List[str] = field(default_factory=list)
    rejection_reason: str = ""
    confluence_factors: List[str] = field(default_factory=list)

    # ÙØªØ§Ø¯ÛØªØ§
    symbol: str = ""
    timeframe: str = ""
    analysis_time: str = ""


# ÙØ²ÙâÙØ§Û ÙØ± Ø¨Ø®Ø´ Ø¯Ø± Ø§ÙØªÛØ§Ø² ÙÙØ§ÛÛ
SCORE_WEIGHTS = {
    "mtf_alignment": 0.25,     # ÙÙØ³ÙÛÛ Multi-Timeframe
    "smc": 0.35,               # Smart Money Concept
    "price_action": 0.20,      # Price Action
    "risk_quality": 0.10,      # Ú©ÛÙÛØª Ø±ÛØ³Ú©
    "session": 0.10,           # Ø³Ø´Ù Ù Kill Zone
}

# Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² ÙØ± ÙØ±Ø­ÙÙ Ø¨Ø±Ø§Û Ø§Ø¯Ø§ÙÙ
STAGE_MINIMUM_SCORES = {
    DecisionStage.MULTI_TIMEFRAME: 40.0,
    DecisionStage.SMC_SCORING: 45.0,
    DecisionStage.PRICE_ACTION_SCORING: 30.0,
    DecisionStage.RISK_FILTER: 50.0,
}

# Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² ÙÙØ§ÛÛ Ø¨Ø±Ø§Û ÙØ±ÙØ¯ Ø¨Ù ÙØ¹Ø§ÙÙÙ
MINIMUM_ENTRY_SCORE = 65.0


class MultiTimeframeEngine:
    """
    ÙÙØªÙØ± ØªØ­ÙÛÙ Multi-Timeframe

    ØªØ­ÙÛÙ Ø³Ù Ø³Ø·Ø­ ØªØ§ÛÙâÙØ±ÛÙ Ù ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² ÙÙØ³ÙÛÛ
    """

    # ÙÚ¯Ø§Ø´Øª ØªØ§ÛÙâÙØ±ÛÙâÙØ§ Ø¨Ù Ø³Ø·ÙØ­
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
        ØªØ­ÙÛÙ Ú©Ø§ÙÙ Multi-Timeframe

        Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§:
            symbol: ÙÙØ§Ø¯ ÙØ¹Ø§ÙÙØ§ØªÛ
            base_timeframe: ØªØ§ÛÙâÙØ±ÛÙ Ù¾Ø§ÛÙ ØªØ­ÙÛÙ
            smc_engine_results: ÙØªØ§ÛØ¬ SMC Ø¨Ø±Ø§Û ÙØ± ØªØ§ÛÙâÙØ±ÛÙ
            pa_engine_results: ÙØªØ§ÛØ¬ PA Ø¨Ø±Ø§Û ÙØ± ØªØ§ÛÙâÙØ±ÛÙ
        """
        levels = self.TIMEFRAME_LEVELS.get(base_timeframe, self.TIMEFRAME_LEVELS["H1"])

        htf_tf = levels["htf"]
        mtf_tf = levels["mtf"]
        ltf_tf = levels["ltf"]

        # ØªØ­ÙÛÙ ÙØ± Ø³Ø·Ø­
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

        # ÙØ­Ø§Ø³Ø¨Ù ÙÙØ³ÙÛÛ
        htf_mtf_aligned = self._are_trends_aligned(htf_analysis.trend, mtf_analysis.trend)
        mtf_ltf_aligned = self._are_trends_aligned(mtf_analysis.trend, ltf_analysis.trend)
        all_aligned = htf_mtf_aligned and mtf_ltf_aligned

        # ØªØ¹ÛÛÙ Ø¬ÙØª Ú©ÙÛ
        overall_direction = self._determine_overall_direction(
            htf_analysis.trend, mtf_analysis.trend, ltf_analysis.trend
        )

        # ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² ÙÙØ³ÙÛÛ
        alignment_score = self._calculate_alignment_score(
            htf_analysis, mtf_analysis, ltf_analysis,
            htf_mtf_aligned, mtf_ltf_aligned, all_aligned
        )

        # Ø§ÙØªÛØ§Ø² Ú©ÙÛ MTF
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
        ØªØ­ÙÛÙ ÛÚ© ØªØ§ÛÙâÙØ±ÛÙ Ø®Ø§Øµ

        Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§:
            timeframe: ÙØ§Ù ØªØ§ÛÙâÙØ±ÛÙ
            level: Ø³Ø·Ø­ (HTF/MTF/LTF)
            smc_data: Ø¯Ø§Ø¯ÙâÙØ§Û SMC
            pa_data: Ø¯Ø§Ø¯ÙâÙØ§Û PA
            reference_trend: Ø±ÙÙØ¯ ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§ØªØ±
        """
        # Ø§Ø³ØªØ®Ø±Ø§Ø¬ Ø±ÙÙØ¯ Ø§Ø² Ø¯Ø§Ø¯ÙâÙØ§Û SMC
        trend = self._extract_trend(smc_data)

        # ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ø³Ø§Ø®ØªØ§Ø±
        structure_score = self._calculate_structure_score(smc_data)

        # Ø¨Ø±Ø±Ø³Û ÙØ§Ø­ÛÙ Ú©ÙÛØ¯Û
        in_key_zone, zone_type, zone_score = self._check_key_zone(smc_data)

        # ÙØ­Ø§Ø³Ø¨Ù ÙÙÙÙØªÙÙ
        momentum_score = self._calculate_momentum(pa_data)

        # Ø¨Ø±Ø±Ø³Û ÙÙØ³ÙÛÛ Ø¨Ø§ ØªØ§ÛÙâÙØ±ÛÙ Ø¨Ø§ÙØ§
        aligned = self._are_trends_aligned(trend, reference_trend) if reference_trend else True

        # Ø´ÙØ§Ø±Ø´ Ø¹ÙØ§ÙÙ ÙÙÚ¯Ø±Ø§
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
        """Ø§Ø³ØªØ®Ø±Ø§Ø¬ Ø¬ÙØª Ø±ÙÙØ¯ Ø§Ø² Ø¯Ø§Ø¯ÙâÙØ§Û SMC"""
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
        """ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ø³Ø§Ø®ØªØ§Ø± Ø¨Ø§Ø²Ø§Ø±"""
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
        Ø¨Ø±Ø±Ø³Û Ø­Ø¶ÙØ± Ø¯Ø± ÙØ§Ø­ÛÙ Ú©ÙÛØ¯Û

        Ø¨Ø±ÙÛâÚ¯Ø±Ø¯Ø§ÙØ¯: (Ø¯Ø± ÙØ§Ø­ÛÙ Ø§Ø³ØªØ ÙÙØ¹ ÙØ§Ø­ÛÙØ Ø§ÙØªÛØ§Ø² ÙØ§Ø­ÛÙ)
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
        """ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² ÙÙÙÙØªÙÙ Ø§Ø² Ø¯Ø§Ø¯ÙâÙØ§Û PA"""
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
        """Ø¨Ø±Ø±Ø³Û ÙÙØ³ÙÛÛ Ø¯Ù Ø±ÙÙØ¯"""
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
        """ØªØ¹ÛÛÙ Ø¬ÙØª Ú©ÙÛ Ø¨Ø§Ø²Ø§Ø± Ø§Ø² Ø³Ù ØªØ§ÛÙâÙØ±ÛÙ"""
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
        """ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ú©ÛÙÛØª ÙÙØ³ÙÛÛ"""
        score = 0.0

        if all_aligned:
            score += 50.0
        elif htf_mtf_aligned:
            score += 30.0
        elif mtf_ltf_aligned:
            score += 20.0

        # Ø¨ÙÙÙØ³ Ø¨Ø±Ø§Û ÙØ§Ø­ÛÙ Ú©ÙÛØ¯Û Ø¯Ø± MTF
        if mtf.in_key_zone:
            score += 25.0

        # Ø¨ÙÙÙØ³ Ø¨Ø±Ø§Û Ú©ÙÙÙÙØ¦ÙØ³ Ø¨Ø§ÙØ§
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
        """Ø´ÙØ§Ø±Ø´ Ø¹ÙØ§ÙÙ ÙÙÚ¯Ø±Ø§"""
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
    ÙÙØªÙØ± Ø§ØµÙÛ ØªØµÙÛÙâÚ¯ÛØ±Û - Stage-Based

    Ø§ÛÙ Ú©ÙØ§Ø³ ØªÙØ§Ù ÙØ±Ø§Ø­Ù ØªØ­ÙÛÙ Ø±Ø§ Ø§Ø¬Ø±Ø§ Ú©Ø±Ø¯Ù Ù ØªØµÙÛÙ ÙÙØ§ÛÛ Ø±Ø§ ÙÛâÚ¯ÛØ±Ø¯.
    ÙØ± ÙØ±Ø­ÙÙ ÙÛâØªÙØ§ÙØ¯ ÙØ±Ø¢ÛÙØ¯ Ø±Ø§ ÙØªÙÙÙ Ú©ÙØ¯ Ø§Ú¯Ø± Ø§ÙØªÛØ§Ø² Ú©Ø§ÙÛ ÙØ¨Ø§Ø´Ø¯.
    """

    def __init__(
        self,
        minimum_entry_score: float = MINIMUM_ENTRY_SCORE,
        enabled_modules: Optional[Dict[str, bool]] = None
    ):
        """
        ÙÙØ¯Ø§Ø±Ø¯ÙÛ Ø§ÙÙÛÙ ÙÙØªÙØ± ØªØµÙÛÙâÚ¯ÛØ±Û

        Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§:
            minimum_entry_score: Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø² Ø¨Ø±Ø§Û ÙØ±ÙØ¯ Ø¨Ù ÙØ¹Ø§ÙÙÙ
            enabled_modules: ÙØ§ÚÙÙâÙØ§Û ÙØ¹Ø§Ù (Ø§ÙÚ©Ø§Ù ØºÛØ±ÙØ¹Ø§Ù Ú©Ø±Ø¯Ù)
        """
        self.minimum_entry_score = minimum_entry_score
        self.mtf_engine = MultiTimeframeEngine()

        # ÙØ§ÚÙÙâÙØ§Û ÙØ¹Ø§Ù - ÙÙÙ Ø¨Ù ØµÙØ±Øª Ù¾ÛØ´ÙØ±Ø¶ ÙØ¹Ø§Ù
        self.enabled_modules = enabled_modules or {
            "multi_timeframe": True,
            "smc": True,
            "price_action": True,
            "risk_filter": True,
            "session_filter": True,
        }

        logger.info(
            f"ÙÙØªÙØ± ØªØµÙÛÙâÚ¯ÛØ±Û Ø¢ÙØ§Ø¯Ù - Ø­Ø¯Ø§ÙÙ Ø§ÙØªÛØ§Ø²: {minimum_entry_score}"
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
        Ø§Ø¬Ø±Ø§Û Ú©Ø§ÙÙ ÙØ±Ø¢ÛÙØ¯ ØªØµÙÛÙâÚ¯ÛØ±Û ÚÙØ¯ÙØ±Ø­ÙÙâØ§Û

        Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§:
            symbol: ÙÙØ§Ø¯ ÙØ¹Ø§ÙÙØ§ØªÛ
            timeframe: ØªØ§ÛÙâÙØ±ÛÙ Ù¾Ø§ÛÙ
            smc_results: ÙØªØ§ÛØ¬ Ú©Ø§ÙÙ ÙÙØªÙØ± SMC
            pa_results: ÙØªØ§ÛØ¬ Ú©Ø§ÙÙ ÙÙØªÙØ± PA
            market_context: Ø§Ø·ÙØ§Ø¹Ø§Øª Ø¨Ø§Ø²Ø§Ø± (ÙÙØ¬ÙØ¯ÛØ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²Ø ...)
        """
        result = DecisionResult(
            symbol=symbol,
            timeframe=timeframe,
            analysis_time=datetime.now(timezone.utc).isoformat(),
            minimum_required_score=self.minimum_entry_score
        )

        logger.info(f"[{symbol}][{timeframe}] Ø´Ø±ÙØ¹ ÙØ±Ø¢ÛÙØ¯ ØªØµÙÛÙâÚ¯ÛØ±Û")

        # ===== ÙØ±Ø­ÙÙ Û±: ÙÛÙØªØ± Ø§ÙÙÛÙ =====
        passed, reason = self._stage_initial_filter(symbol, timeframe, market_context, result)
        if not passed:
            result.decision = "NO_TRADE"
            result.rejection_reason = reason
            logger.info(f"[{symbol}] Ø±Ø¯ Ø¯Ø± ÙØ±Ø­ÙÙ ÙÛÙØªØ± Ø§ÙÙÛÙ: {reason}")
            return result

        # ===== ÙØ±Ø­ÙÙ Û²: ØªØ­ÙÛÙ Multi-Timeframe =====
        if self.enabled_modules.get("multi_timeframe", True):
            mtf_result = self._stage_multi_timeframe(symbol, timeframe, smc_results, pa_results, result)
            result.mtf_result = mtf_result
            result.mtf_score = mtf_result.total_score

            if result.mtf_score < STAGE_MINIMUM_SCORES[DecisionStage.MULTI_TIMEFRAME]:
                result.decision = "NO_TRADE"
                result.rejection_reason = f"Ø§ÙØªÛØ§Ø² MTF ÙØ§Ú©Ø§ÙÛ: {result.mtf_score:.1f}"
                return result

        # ===== ÙØ±Ø­ÙÙ Û³: Ø§ÙØªÛØ§Ø²Ø¯ÙÛ SMC =====
        if self.enabled_modules.get("smc", True):
            smc_score_result = self._stage_smc_scoring(smc_results.get(timeframe, {}), result)
            result.smc_result = smc_score_result
            result.smc_score = smc_score_result.total_score

            if result.smc_score < STAGE_MINIMUM_SCORES[DecisionStage.SMC_SCORING]:
                result.decision = "NO_TRADE"
                result.rejection_reason = f"Ø§ÙØªÛØ§Ø² SMC ÙØ§Ú©Ø§ÙÛ: {result.smc_score:.1f}"
                return result

        # ===== ÙØ±Ø­ÙÙ Û´: Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Price Action =====
        if self.enabled_modules.get("price_action", True):
            pa_score_result = self._stage_pa_scoring(pa_results.get(timeframe, {}), result)
            result.pa_result = pa_score_result
            result.pa_score = pa_score_result.total_score

        # ===== ÙØ±Ø­ÙÙ Ûµ: ÙÛÙØªØ± Ø±ÛØ³Ú© =====
        if self.enabled_modules.get("risk_filter", True):
            risk_assessment = self._stage_risk_filter(symbol, market_context, result)
            result.risk_assessment = risk_assessment
            result.risk_score = risk_assessment.risk_score

            if not risk_assessment.rr_pass or not risk_assessment.daily_loss_pass:
                result.decision = "NO_TRADE"
                result.rejection_reason = f"ÙÛÙØªØ± Ø±ÛØ³Ú©: {', '.join(risk_assessment.rejection_reasons)}"
                return result

        # ===== ÙØ±Ø­ÙÙ Û¶: ØªØµÙÛÙ ÙÙØ§ÛÛ =====
        self._stage_final_decision(result)

        logger.info(
            f"[{symbol}][{timeframe}] ØªØµÙÛÙ: {result.decision} | "
            f"Ø§ÙØªÛØ§Ø²: {result.total_score:.1f}"
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
        ÙØ±Ø­ÙÙ Û±: ÙÛÙØªØ± Ø§ÙÙÛÙ

        Ø¨Ø±Ø±Ø³ÛâÙØ§Û Ù¾Ø§ÛÙ ÙØ¨Ù Ø§Ø² Ø´Ø±ÙØ¹ ØªØ­ÙÛÙ Ø§ØµÙÛ
        """
        result.stage_log.append(f"â ÙØ±Ø­ÙÙ Û±: ÙÛÙØªØ± Ø§ÙÙÛÙ Ø´Ø±ÙØ¹ Ø´Ø¯")

        # Ø¨Ø±Ø±Ø³Û ÙØ¹Ø§Ù Ø¨ÙØ¯Ù Ø±Ø¨Ø§Øª
        if not context.get("bot_running", True):
            return False, "Ø±Ø¨Ø§Øª Ø¯Ø± Ø­Ø§ÙØª ÙØªÙÙÙ Ø§Ø³Øª"

        # Ø¨Ø±Ø±Ø³Û ÙØ¬Ø§Ø² Ø¨ÙØ¯Ù ÙÙØ§Ø¯
        allowed_symbols = context.get("allowed_symbols", [])
        if allowed_symbols and symbol not in allowed_symbols:
            return False, f"ÙÙØ§Ø¯ {symbol} ÙØ¬Ø§Ø² ÙÛØ³Øª"

        # Ø¨Ø±Ø±Ø³Û Ø³Ø§Ø¹Øª ÙØ¹Ø§ÙÙØ§ØªÛ
        if not context.get("trading_hours_active", True):
            return False, "Ø®Ø§Ø±Ø¬ Ø§Ø² Ø³Ø§Ø¹Øª ÙØ¹Ø§ÙÙØ§ØªÛ"

        # Ø¨Ø±Ø±Ø³Û ÙÙØ³Ø§ÙØ§Øª Ø¨Ø§Ø²Ø§Ø±
        current_spread = context.get("current_spread", 0)
        max_spread = context.get("max_allowed_spread", 30)
        if current_spread > max_spread:
            return False, f"Ø§Ø³Ù¾Ø±Ø¯ Ø¨Ø§ÙØ§: {current_spread} > {max_spread}"

        result.stage_log.append("â ÙÛÙØªØ± Ø§ÙÙÛÙ Ù¾Ø§Ø³ Ø´Ø¯")
        return True, ""

    def _stage_multi_timeframe(
        self,
        symbol: str,
        timeframe: str,
        smc_results: Dict[str, Any],
        pa_results: Dict[str, Any],
        result: DecisionResult
    ) -> MultiTimeframeResult:
        """ÙØ±Ø­ÙÙ Û²: ØªØ­ÙÛÙ Multi-Timeframe"""
        result.stage_log.append("ð ÙØ±Ø­ÙÙ Û²: ØªØ­ÙÛÙ Multi-Timeframe")

        mtf_result = self.mtf_engine.analyze(symbol, timeframe, smc_results, pa_results)

        result.stage_log.append(
            f"  HTF: {mtf_result.htf.trend.value} | "
            f"MTF: {mtf_result.mtf.trend.value} | "
            f"LTF: {mtf_result.ltf.trend.value} | "
            f"ÙÙØ³Ù: {'Ø¨ÙÙ' if mtf_result.all_aligned else 'Ø®ÛØ±'} | "
            f"Ø§ÙØªÛØ§Ø²: {mtf_result.total_score:.1f}"
        )

        return mtf_result

    def _stage_smc_scoring(
        self,
        smc_data: Dict[str, Any],
        result: DecisionResult
    ) -> SMCScoreResult:
        """
        ÙØ±Ø­ÙÙ Û³: Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Ú©Ø§ÙÙ SMC

        ÙØ± ÙÙÙÙÙ SMC Ø§ÙØªÛØ§Ø² Ø¬Ø¯Ø§Ú¯Ø§ÙÙ Ø¯Ø±ÛØ§ÙØª ÙÛâÚ©ÙØ¯
        """
        result.stage_log.append("ð§  ÙØ±Ø­ÙÙ Û³: Ø§ÙØªÛØ§Ø²Ø¯ÙÛ SMC")

        smc = SMCScoreResult()

        # ====== Ø³Ø§Ø®ØªØ§Ø± Ø¨Ø§Ø²Ø§Ø± ======
        ms = smc_data.get("market_structure", {})

        # BOS - Ø´Ú©Ø³Øª Ø³Ø§Ø®ØªØ§Ø±
        if ms.get("bos_confirmed"):
            smc.bos_confirmed = True
            bos_quality = ms.get("bos_quality", 0.5)
            smc.market_structure_score += 25.0 * bos_quality
            result.confluence_factors.append("BOS ØªØ£ÛÛØ¯ Ø´Ø¯")

        # CHOCH - ØªØºÛÛØ± Ú©Ø§Ø±Ø§Ú©ØªØ±
        if ms.get("choch_detected"):
            smc.choch_confirmed = True
            choch_quality = ms.get("choch_quality", 0.5)
            smc.market_structure_score += 20.0 * choch_quality
            result.confluence_factors.append("CHOCH Ø´ÙØ§Ø³Ø§ÛÛ Ø´Ø¯")

        # MSS - Ø´Ú©Ø³Øª Ø³Ø§Ø®ØªØ§Ø± Ø§ØµÙÛ
        if ms.get("mss_detected"):
            smc.mss_confirmed = True
            smc.market_structure_score += 15.0

        smc.market_structure_score = min(100.0, smc.market_structure_score)

        # ====== Order Block ======
        obs = smc_data.get("order_blocks", [])
        best_ob = max(obs, key=lambda x: x.get("score", 0), default=None) if obs else None
        if best_ob and best_ob.get("price_in_zone"):
            smc.order_block_score = min(100.0, best_ob.get("score", 0) * 100)
            result.confluence_factors.append(f"Order Block ÙØ¹Ø§Ù ({smc.order_block_score:.0f})")

        # ====== FVG ======
        fvgs = smc_data.get("fvg_zones", [])
        best_fvg = max(fvgs, key=lambda x: x.get("score", 0), default=None) if fvgs else None
        if best_fvg and best_fvg.get("price_in_zone"):
            smc.fvg_score = min(100.0, best_fvg.get("score", 0) * 100)
            result.confluence_factors.append(f"FVG ÙØ¹Ø§Ù ({smc.fvg_score:.0f})")

        # ====== Liquidity ======
        liq = smc_data.get("liquidity", {})
        if liq.get("sweep_detected"):
            smc.liquidity_sweep_confirmed = True
            smc.external_liquidity_score = min(100.0, liq.get("sweep_quality", 0.5) * 100)
            result.confluence_factors.append("Liquidity Sweep ØªØ£ÛÛØ¯ Ø´Ø¯")

        smc.internal_liquidity_score = min(100.0, liq.get("internal_liq_score", 0) * 100)

        # ====== Premium/Discount ======
        pd_zone = smc_data.get("premium_discount", {})
        if pd_zone.get("in_discount_for_buy") or pd_zone.get("in_premium_for_sell"):
            smc.premium_discount_score = min(100.0, pd_zone.get("quality_score", 0.5) * 100)
            result.confluence_factors.append("Ø¯Ø± ÙØ§Ø­ÛÙ Premium/Discount ÙÙØ§Ø³Ø¨")

        # ====== Kill Zone ======
        if smc_data.get("kill_zone_active"):
            smc.kill_zone_active = True
            smc.session_liquidity_score = 80.0
            result.confluence_factors.append("Kill Zone ÙØ¹Ø§Ù")

        # ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ú©ÙÛ SMC Ø¨Ø§ ÙØ²ÙâØ¯ÙÛ
        smc.total_score = (
            smc.market_structure_score * 0.30 +
            smc.order_block_score * 0.20 +
            smc.fvg_score * 0.15 +
            smc.external_liquidity_score * 0.15 +
            smc.premium_discount_score * 0.10 +
            smc.session_liquidity_score * 0.10
        )

        smc.confidence = min(1.0, len(result.confluence_factors) / 6.0)

        result.stage_log.append(f"  SMC Ø§ÙØªÛØ§Ø²: {smc.total_score:.1f} | Ú©ÙÙÙÙØ¦ÙØ³: {len(result.confluence_factors)}")

        return smc

    def _stage_pa_scoring(
        self,
        pa_data: Dict[str, Any],
        result: DecisionResult
    ) -> PAScoreResult:
        """
        ÙØ±Ø­ÙÙ Û´: Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Price Action

        ÙØ± Ø§ÙÚ¯ÙÛ Ø´ÙØ¹Û Ø§ÙØªÛØ§Ø² Ø¨Ø± Ø§Ø³Ø§Ø³ Ú©ÛÙÛØª Ù ÙÙÙØ¹ÛØª Ø¯Ø±ÛØ§ÙØª ÙÛâÚ©ÙØ¯
        """
        result.stage_log.append("ð ÙØ±Ø­ÙÙ Û´: Ø§ÙØªÛØ§Ø²Ø¯ÙÛ Price Action")

        pa = PAScoreResult()

        patterns = pa_data.get("detected_patterns", {})

        # ====== Ø§ÙÚ¯ÙÙØ§Û ØµØ¹ÙØ¯Û ======
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

        # ====== Ø§ÙÚ¯ÙÙØ§Û ÙØ²ÙÙÛ ======
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

        # ====== Ø§ÙÚ¯ÙÙØ§Û Ø³Ø§Ø®ØªØ§Ø±Û ======
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
            result.confluence_factors.append("Retest ØªØ£ÛÛØ¯ Ø´Ø¯")

        if pa_data.get("compression_detected"):
            pa.compression_score = 70.0
            result.confluence_factors.append("Compression Ø´ÙØ§Ø³Ø§ÛÛ Ø´Ø¯")

        if pa_data.get("expansion_detected"):
            pa.expansion_score = min(100.0, pa_data.get("expansion_quality", 0.5) * 100)

        # ØªØ¹ÛÛÙ Ø¬ÙØª ØºØ§ÙØ¨
        if pa.bullish_signals > pa.bearish_signals:
            pa.dominant_direction = "bullish"
        elif pa.bearish_signals > pa.bullish_signals:
            pa.dominant_direction = "bearish"
        else:
            pa.dominant_direction = "neutral"

        # ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ú©ÙÛ
        all_scores = [
            pa.pin_bar_score, pa.engulfing_score, pa.fakey_score,
            pa.inside_bar_score, pa.morning_star_score, pa.evening_star_score,
            pa.three_soldiers_score, pa.three_crows_score,
            pa.breakout_score, pa.retest_score
        ]

        nonzero_scores = [s for s in all_scores if s > 0]
        pa.total_score = sum(nonzero_scores) / len(nonzero_scores) if nonzero_scores else 0.0

        # Ø¨ÙÙÙØ³ Ø¨Ø±Ø§Û ÚÙØ¯ Ø§ÙÚ¯ÙÛ ÙÙØ²ÙØ§Ù
        if len(nonzero_scores) >= 2:
            pa.total_score = min(100.0, pa.total_score * 1.15)

        result.stage_log.append(
            f"  PA Ø§ÙØªÛØ§Ø²: {pa.total_score:.1f} | "
            f"ØµØ¹ÙØ¯Û: {pa.bullish_signals} | ÙØ²ÙÙÛ: {pa.bearish_signals}"
        )

        return pa

    def _stage_risk_filter(
        self,
        symbol: str,
        context: Dict[str, Any],
        result: DecisionResult
    ) -> RiskAssessment:
        """
        ÙØ±Ø­ÙÙ Ûµ: ÙÛÙØªØ± Ø±ÛØ³Ú©

        ØªÙØ§Ù Ù¾Ø§Ø±Ø§ÙØªØ±ÙØ§Û Ø±ÛØ³Ú© Ø§Ø±Ø²ÛØ§Ø¨Û ÙÛâØ´ÙØ¯
        """
        result.stage_log.append("âï¸ ÙØ±Ø­ÙÙ Ûµ: ÙÛÙØªØ± Ø±ÛØ³Ú©")

        risk = RiskAssessment()

        # ÙØ³Ø¨Øª Ø±ÛØ³Ú© Ø¨Ù Ø±ÛÙØ§Ø±Ø¯
        risk.risk_reward_ratio = context.get("risk_reward_ratio", 0.0)
        min_rr = context.get("min_risk_reward", 1.5)
        risk.rr_pass = risk.risk_reward_ratio >= min_rr
        if not risk.rr_pass:
            risk.rejection_reasons.append(f"RR ÙØ§Ú©Ø§ÙÛ: {risk.risk_reward_ratio:.2f} < {min_rr}")

        # Ø¶Ø±Ø± Ø±ÙØ²Ø§ÙÙ
        daily_loss = context.get("daily_loss_amount", 0)
        max_daily_loss = context.get("max_daily_loss", float("inf"))
        risk.daily_loss_pass = daily_loss < max_daily_loss
        if not risk.daily_loss_pass:
            risk.rejection_reasons.append(f"Ø­Ø¯Ø§Ú©Ø«Ø± Ø¶Ø±Ø± Ø±ÙØ²Ø§ÙÙ: {daily_loss:.2f}$")

        # ØªØ¹Ø¯Ø§Ø¯ ÙØ¹Ø§ÙÙØ§Øª ÙÙØ²ÙØ§Ù
        open_trades = context.get("open_trades_count", 0)
        max_trades = context.get("max_simultaneous_trades", 3)
        risk.max_trades_pass = open_trades < max_trades
        if not risk.max_trades_pass:
            risk.rejection_reasons.append(f"ØªØ¹Ø¯Ø§Ø¯ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²: {open_trades}/{max_trades}")

        # ÙÙØ³Ø§ÙØ§Øª
        current_volatility = context.get("current_volatility", "medium")
        risk.volatility_pass = current_volatility != "extreme"

        # Ø§Ø³Ù¾Ø±Ø¯
        current_spread = context.get("current_spread", 0)
        max_spread = context.get("max_allowed_spread", 30)
        risk.spread_pass = current_spread <= max_spread

        # Ø¯Ø±ØµØ¯ Ø±ÛØ³Ú©
        risk.risk_percent = context.get("risk_percent_per_trade", 1.0)

        # ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ø±ÛØ³Ú©
        passed_checks = sum([
            risk.rr_pass, risk.daily_loss_pass,
            risk.max_trades_pass, risk.volatility_pass, risk.spread_pass
        ])
        risk.risk_score = (passed_checks / 5) * 100

        result.stage_log.append(
            f"  RR: {risk.risk_reward_ratio:.2f} | "
            f"ÚÚ©âÙØ§Û Ù¾Ø§Ø³: {passed_checks}/5 | "
            f"Ø§ÙØªÛØ§Ø²: {risk.risk_score:.1f}"
        )

        return risk

    def _stage_final_decision(self, result: DecisionResult):
        """
        ÙØ±Ø­ÙÙ Û¶: ØªØµÙÛÙ ÙÙØ§ÛÛ Ø¨Ø§ ÙØ²ÙâØ¯ÙÛ

        Ø¬ÙØ¹âØ¨ÙØ¯Û ØªÙØ§Ù Ø§ÙØªÛØ§Ø²Ø§Øª Ù ØªØµÙÛÙâÚ¯ÛØ±Û ÙÙØ§ÛÛ
        """
        result.stage_log.append("ð¯ ÙØ±Ø­ÙÙ Û¶: ØªØµÙÛÙ ÙÙØ§ÛÛ")

        # ÙØ­Ø§Ø³Ø¨Ù Ø§ÙØªÛØ§Ø² Ú©ÙÛ Ø¨Ø§ ÙØ²ÙâØ¯ÙÛ
        result.total_score = (
            result.mtf_score * SCORE_WEIGHTS["mtf_alignment"] +
            result.smc_score * SCORE_WEIGHTS["smc"] +
            result.pa_score * SCORE_WEIGHTS["price_action"] +
            result.risk_score * SCORE_WEIGHTS["risk_quality"] +
            result.session_score * SCORE_WEIGHTS["session"]
        )

        # ØªØ¹ÛÛÙ Ø¬ÙØª Ù¾ÛØ´ÙÙØ§Ø¯Û
        suggested_direction = self._determine_suggested_direction(result)
        result.suggested_direction = suggested_direction

        # ØªØµÙÛÙ ÙÙØ§ÛÛ
        if result.total_score >= self.minimum_entry_score:
            if suggested_direction == "bullish":
                result.decision = "BUY"
            elif suggested_direction == "bearish":
                result.decision = "SELL"
            else:
                result.decision = "NO_TRADE"
                result.rejection_reason = "Ø¬ÙØª ÙØ§ÙØ´Ø®Øµ"
        else:
            result.decision = "NO_TRADE"
            result.rejection_reason = (
                f"Ø§ÙØªÛØ§Ø² ÙØ§Ú©Ø§ÙÛ: {result.total_score:.1f} < {self.minimum_entry_score}"
            )

        result.stage_log.append(
            f"  Ø§ÙØªÛØ§Ø² Ú©Ù: {result.total_score:.1f} | "
            f"Ø­Ø¯Ø§ÙÙ: {self.minimum_entry_score} | "
            f"ØªØµÙÛÙ: {result.decision}"
        )

    def _determine_suggested_direction(self, result: DecisionResult) -> str:
        """ØªØ¹ÛÛÙ Ø¬ÙØª Ù¾ÛØ´ÙÙØ§Ø¯Û Ø§Ø² ØªØ±Ú©ÛØ¨ MTF Ù PA Ù SMC"""
        bullish_votes = 0
        bearish_votes = 0

        # Ø±Ø£Û MTF
        if result.mtf_result:
            if result.mtf_result.overall_direction == TrendDirection.BULLISH:
                bullish_votes += 3
            elif result.mtf_result.overall_direction == TrendDirection.BEARISH:
                bearish_votes += 3

        # Ø±Ø£Û SMC
        if result.smc_result:
            if result.smc_result.bos_confirmed and result.smc_result.liquidity_sweep_confirmed:
                # Ø¬ÙØª Ø§Ø² BOS Ù Liquidity ØªØ¹ÛÛÙ ÙÛâØ´ÙØ¯
                smc_raw = {}
                if result.mtf_result and result.mtf_result.ltf.raw_data.get("smc"):
                    smc_raw = result.mtf_result.ltf.raw_data["smc"]

                bos_dir = smc_raw.get("market_structure", {}).get("last_bos_direction", "")
                if bos_dir == "bullish":
                    bullish_votes += 2
                elif bos_dir == "bearish":
                    bearish_votes += 2

        # Ø±Ø£Û PA
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


# =============================================================================
# =================== CONTRACT LAYER (Service Interface) ======================
# =============================================================================
# این بخش اشیاء قراردادی را تعریف می‌کند که decision_service.py با آن‌ها کار می‌کند.
# make_decision() به‌عنوان bridge بین این لایه و موتور داخلی decide() عمل می‌کند.
# =============================================================================

from dataclasses import dataclass as _dataclass
from typing import List as _List, Optional as _Optional, Dict as _Dict, Any as _Any
from datetime import datetime as _datetime
from enum import Enum as _Enum


# --- Enums مورد نیاز سرویس ---

class ReasonCode(_Enum):
    """کدهای دلیل تصمیم"""
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
    """کدهای دلیل رد تصمیم"""
    MTF_FAILED = "mtf_failed"
    SMC_FAILED = "smc_failed"
    PA_FAILED = "pa_failed"
    RISK_FAILED = "risk_failed"
    SESSION_CLOSED = "session_closed"
    LOW_SCORE = "low_score"
    SYMBOL_BLOCKED = "symbol_blocked"
    LICENSE_INVALID = "license_invalid"
    VOLATILITY_TOO_HIGH = "volatility_too_high"


# --- Context dataclasses (ورودی‌های غنی سرویس) ---

@_dataclass
class SMCContext:
    """زمینه تحلیل Smart Money Concepts"""
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
    """زمینه تحلیل Price Action"""
    direction: _Any = "neutral"
    direction_score: float = 0.0
    patterns: _List[str] = None
    candle_strength: str = "none"

    def __post_init__(self):
        if self.patterns is None:
            self.patterns = []


@_dataclass
class SessionContext:
    """زمینه سشن معاملاتی"""
    current_session: _Any = "closed"
    killzone_active: bool = False
    killzone_name: _Optional[str] = None
    session_score: float = 0.0
    session_overlap: bool = False


@_dataclass
class LicenseContext:
    """زمینه مجوز"""
    is_valid: bool = True
    is_expired: bool = False
    license_type: str = "trial"
    allowed_features: _List[str] = None
    max_devices: int = 1
    devices_used: int = 0

    def __post_init__(self):
        if self.allowed_features is None:
            self.allowed_features = []


@_dataclass
class RiskContext:
    """زمینه مدیریت ریسک"""
    daily_pnl: float = 0.0
    daily_trades: int = 0
    open_positions: int = 0
    max_daily_loss: float = -500.0
    max_daily_trades: int = 5
    max_positions: int = 3
    risk_per_trade: float = 0.02
    available_margin: float = 0.0


@_dataclass
class SymbolPolicy:
    """سیاست نماد"""
    symbol: str = ""
    allowed: bool = True
    max_lot: float = 1.0
    min_lot: float = 0.01
    max_spread: float = 5.0
    max_slippage: float = 3.0
    allowed_sessions: _List[str] = None
    blocked_reason: _Optional[str] = None

    def __post_init__(self):
        if self.allowed_sessions is None:
            self.allowed_sessions = []


@_dataclass
class VolatilityContext:
    """زمینه نوسان بازار"""
    atr: float = 0.0
    atr_percentile: int = 0
    volatility_level: _Any = "medium"
    spread: float = 0.0
    spread_percentile: int = 0


@_dataclass
class MultiTimeframeContext:
    """زمینه تحلیل چند تایم‌فریمی"""
    higher_timeframe_trend: _Any = "ranging"
    htf_alignment: bool = False
    htf_score: float = 0.0
    lower_timeframe_entry: bool = False
    ltf_score: float = 0.0


@_dataclass
class LiquidityContext:
    """زمینه نقدینگی"""
    state: _Any = "none"
    buy_side_liquidity: _List[_Dict[str, _Any]] = None
    sell_side_liquidity: _List[_Dict[str, _Any]] = None
    sweep_score: float = 0.0

    def __post_init__(self):
        if self.buy_side_liquidity is None:
            self.buy_side_liquidity = []
        if self.sell_side_liquidity is None:
            self.sell_side_liquidity = []


# --- Input / Output dataclasses ---

@_dataclass
class DecisionInput:
    """ورودی کامل موتور تصمیم‌گیری"""
    symbol: str
    timeframe: str
    current_price: float = 0.0
    smc_context: _Optional[SMCContext] = None
    price_action_context: _Optional[PriceActionContext] = None
    mtf_context: _Optional[MultiTimeframeContext] = None
    session_context: _Optional[SessionContext] = None
    liquidity_context: _Optional[LiquidityContext] = None
    volatility_context: _Optional[VolatilityContext] = None
    risk_context: _Optional[RiskContext] = None
    license_context: _Optional[LicenseContext] = None
    symbol_policy: _Optional[SymbolPolicy] = None
    user_settings: _Dict[str, _Any] = None

    def __post_init__(self):
        if self.smc_context is None:
            self.smc_context = SMCContext()
        if self.price_action_context is None:
            self.price_action_context = PriceActionContext()
        if self.mtf_context is None:
            self.mtf_context = MultiTimeframeContext()
        if self.session_context is None:
            self.session_context = SessionContext()
        if self.liquidity_context is None:
            self.liquidity_context = LiquidityContext()
        if self.volatility_context is None:
            self.volatility_context = VolatilityContext()
        if self.risk_context is None:
            self.risk_context = RiskContext()
        if self.license_context is None:
            self.license_context = LicenseContext()
        if self.symbol_policy is None:
            self.symbol_policy = SymbolPolicy(symbol=self.symbol)
        if self.user_settings is None:
            self.user_settings = {}


@_dataclass
class TradingLevels:
    """سطوح معاملاتی"""
    entry_zone: float = 0.0
    entry_zone_high: float = 0.0
    entry_zone_low: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0
    invalidation_level: float = 0.0
    risk_reward_ratio: float = 0.0


@_dataclass
class RiskProfile:
    """پروفایل ریسک تصمیم"""
    risk_level: _Any = "medium"
    position_size: float = 0.01
    max_loss_amount: float = 0.0
    potential_profit: float = 0.0
    risk_reward_ratio: float = 0.0


@_dataclass
class DecisionOutput:
    """خروجی کامل موتور تصمیم‌گیری — سازگار با DecisionService"""
    symbol: str
    timeframe: str
    created_at: _datetime
    decision: _Any                          # DecisionAction enum یا str
    direction: _Any                         # DecisionDirection enum یا str
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
# Bridge method — injected into DecisionEngine at module load
# =============================================================================

def _make_decision(self, decision_input: "DecisionInput") -> "DecisionOutput":
    """
    Bridge: DecisionInput → decide() → DecisionOutput

    این متد DecisionInput غنی را به پارامترهای ساده decide() تبدیل می‌کند،
    موتور داخلی را اجرا می‌کند، و DecisionResult را به DecisionOutput تبدیل می‌کند.
    """
    smc = decision_input.smc_context
    pa = decision_input.price_action_context
    mtf = decision_input.mtf_context
    session = decision_input.session_context
    liq = decision_input.liquidity_context
    vol = decision_input.volatility_context
    risk = decision_input.risk_context
    policy = decision_input.symbol_policy
    license_ = decision_input.license_context

    # --- بررسی مجوز ---
    if not license_.is_valid or license_.is_expired:
        return _build_blocked_output(
            decision_input,
            blocked=[BlockedReason.LICENSE_INVALID],
            reasons=["مجوز نامعتبر یا منقضی شده است"]
        )

    # --- بررسی سیاست نماد ---
    if not policy.allowed:
        return _build_blocked_output(
            decision_input,
            blocked=[BlockedReason.SYMBOL_BLOCKED],
            reasons=[policy.blocked_reason or f"نماد {decision_input.symbol} مجاز نیست"]
        )

    # --- ساخت smc_results ---
    tf = decision_input.timeframe
    smc_results = {
        tf: {
            "market_structure": {
                "trend": str(getattr(smc.trend, "value", smc.trend)),
                "trend_score": smc.trend_score,
                "last_bos_direction": smc.structure_direction or "",
                "structure_event": smc.structure_event or "",
                "structure_level": smc.structure_level or 0.0,
            },
            "liquidity": {
                "liquidity_swept": smc.liquidity_swept,
                "sweep_direction": smc.liquidity_direction or "",
                "buy_side": liq.buy_side_liquidity,
                "sell_side": liq.sell_side_liquidity,
                "sweep_score": liq.sweep_score,
            },
            "order_blocks": smc.order_blocks,
            "fvgs": smc.fvgs,
            "swing_high": smc.swing_high or 0.0,
            "swing_low": smc.swing_low or 0.0,
            "premium_discount": smc.premium_discount,
        }
    }

    # --- ساخت pa_results ---
    pa_results = {
        tf: {
            "direction": str(getattr(pa.direction, "value", pa.direction)),
            "direction_score": pa.direction_score,
            "patterns": pa.patterns,
            "candle_strength": pa.candle_strength,
        }
    }

    # --- ساخت market_context ---
    market_context = {
        "symbol_allowed": policy.allowed,
        "session": {
            "current_session": str(getattr(session.current_session, "value", session.current_session)),
            "killzone_active": session.killzone_active,
            "killzone_name": session.killzone_name,
            "session_score": session.session_score,
            "session_overlap": session.session_overlap,
        },
        "volatility": {
            "atr": vol.atr,
            "atr_percentile": vol.atr_percentile,
            "volatility_level": str(getattr(vol.volatility_level, "value", vol.volatility_level)),
            "spread": vol.spread,
            "spread_percentile": vol.spread_percentile,
        },
        "risk": {
            "daily_pnl": risk.daily_pnl,
            "daily_trades": risk.daily_trades,
            "open_positions": risk.open_positions,
            "max_daily_loss": risk.max_daily_loss,
            "max_daily_trades": risk.max_daily_trades,
            "max_positions": risk.max_positions,
            "risk_per_trade": risk.risk_per_trade,
            "available_margin": risk.available_margin,
        },
        "mtf": {
            "htf_trend": str(getattr(mtf.higher_timeframe_trend, "value", mtf.higher_timeframe_trend)),
            "htf_alignment": mtf.htf_alignment,
            "htf_score": mtf.htf_score,
            "ltf_entry": mtf.lower_timeframe_entry,
            "ltf_score": mtf.ltf_score,
        },
        "current_price": decision_input.current_price,
        "max_spread": policy.max_spread,
    }

    # --- اجرای موتور اصلی ---
    result: DecisionResult = self.decide(
        symbol=decision_input.symbol,
        timeframe=decision_input.timeframe,
        smc_results=smc_results,
        pa_results=pa_results,
        market_context=market_context
    )

    # --- تبدیل DecisionResult → DecisionOutput ---
    return _result_to_output(result, decision_input, risk)


def _build_blocked_output(
    decision_input: "DecisionInput",
    blocked: _List[BlockedReason],
    reasons: _List[str]
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
        created_at=_datetime.utcnow(),
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
    """تبدیل DecisionResult (داخلی) به DecisionOutput (قراردادی)"""
    try:
        from ..core.enums import DecisionAction, DecisionDirection
        decision_map = {
            "BUY": DecisionAction.BUY,
            "SELL": DecisionAction.SELL,
            "NO_TRADE": DecisionAction.NO_TRADE,
        }
        direction_map = {
            "bullish": DecisionDirection.LONG,
            "bearish": DecisionDirection.SHORT,
            "neutral": DecisionDirection.NEUTRAL,
        }
        decision_val = decision_map.get(result.decision, DecisionAction.NO_TRADE)
        direction_val = direction_map.get(result.suggested_direction, DecisionDirection.NEUTRAL)
    except Exception:
        decision_val = result.decision
        direction_val = result.suggested_direction or "neutral"

    allowed = result.decision in ("BUY", "SELL")

    # -- reason_codes --
    reason_codes: _List[ReasonCode] = []
    blocked_reasons: _List[BlockedReason] = []

    if result.mtf_score >= 50:
        reason_codes.append(ReasonCode.MTF_ALIGNED)
    else:
        blocked_reasons.append(BlockedReason.MTF_FAILED)

    if result.smc_score >= 50:
        reason_codes.append(ReasonCode.SMC_CONFIRMED)
        if result.smc_result and result.smc_result.liquidity_sweep_confirmed:
            reason_codes.append(ReasonCode.LIQUIDITY_SWEPT)
        if result.smc_result and result.smc_result.order_block_count > 0:
            reason_codes.append(ReasonCode.ORDER_BLOCK_PRESENT)
        if result.smc_result and result.smc_result.fvg_count > 0:
            reason_codes.append(ReasonCode.FVG_PRESENT)
    else:
        blocked_reasons.append(BlockedReason.SMC_FAILED)

    if result.pa_score >= 40:
        reason_codes.append(ReasonCode.PA_CONFIRMED)
    else:
        blocked_reasons.append(BlockedReason.PA_FAILED)

    if not result.rejection_reason:
        reason_codes.append(ReasonCode.RISK_PASSED)
    elif "ریسک" in result.rejection_reason:
        blocked_reasons.append(BlockedReason.RISK_FAILED)
    elif "امتیاز" in result.rejection_reason or "score" in result.rejection_reason.lower():
        blocked_reasons.append(BlockedReason.LOW_SCORE)

    # -- reasons_persian --
    reasons_persian: _List[str] = []
    if result.confluence_factors:
        reasons_persian.extend(result.confluence_factors)
    if result.rejection_reason:
        reasons_persian.append(result.rejection_reason)
    if result.stage_log:
        reasons_persian.extend(result.stage_log[-3:])

    # -- score_breakdown --
    score_breakdown = {
        "mtf": result.mtf_score,
        "smc": result.smc_score,
        "pa": result.pa_score,
        "risk": result.risk_score,
        "session": result.session_score,
        "total": result.total_score,
    }

    # -- trading_levels --
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

    # -- risk_profile --
    risk_profile: _Optional[RiskProfile] = None
    if allowed:
        margin = risk.available_margin or 1.0
        pos_size = round(margin * risk.risk_per_trade / max(abs(result.entry_price - result.stop_loss) * 100000, 1), 2)
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
        created_at=_datetime.utcnow(),
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
