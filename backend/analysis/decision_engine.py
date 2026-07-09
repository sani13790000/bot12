"""
Decision Engine - Signal Confirmation and Trade Decision Logic.

Validates signals from various sources and makes final trading decisions.
Ensures signal confluence before issuing trade commands.
"""

import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import List, Optional, Dict, Tuple
import numpy as np

logger = logging.getLogger(__name__)


class SignalType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class ConfluenceLevel(StrEnum):
    WEAK = "WEAK"        # 1 source
    MODERATE = "MODERATE"  # 2 sources
    STRONG = "STRONG"    # 3+ sources


@dataclass
class Signal:
    """Single signal from an analysis source."""
    type: SignalType
    strength: float  # 0-1
    source: str      # e.g., 'smc', 'price_action', 'ml_model'
    confidence: float  # 0-1
    timestamp: str   # ISO format


@dataclass
class ConfluenceAnalysis:
    """Result of confluence analysis."""
    final_signal: SignalType
    confluence_level: ConfluenceLevel
    score: float  # 0-100
    contributing_signals: List[Signal]
    risk_reward_ratio: float
    stop_loss: float
    take_profit: float
    position_size: float
    rationale: str


class DecisionEngine:
    """Signal confirmation and trade decision engine."""

    def __init__(
        self,
        confluence_threshold: float = 0.6,
        min_sources: int = 2,
        atr_multiplier_sl: float = 2.0,
        atr_multiplier_tp: float = 3.0,
    ):
        """
        Initialize Decision Engine.

        Args:
            confluence_threshold: Minimum score (0-1) for trade entry
            min_sources: Minimum number of confirming sources
            atr_multiplier_sl: Stop loss distance as ATR multiple
            atr_multiplier_tp: Take profit distance as ATR multiple
        """
        self.confluence_threshold = confluence_threshold
        self.min_sources = min_sources
        self.atr_multiplier_sl = atr_multiplier_sl
        self.atr_multiplier_tp = atr_multiplier_tp

    def analyze_confluence(
        self,
        signals: List[Signal],
        current_price: float,
        atr: float,
        symbol: str = "EURUSD"
    ) -> ConfluenceAnalysis:
        """
        Analyze signal confluence and generate trade decision.

        Args:
            signals: List of Signal objects from various sources
            current_price: Current market price
            atr: Average True Range for SL/TP calculation
            symbol: Trading instrument

        Returns:
            ConfluenceAnalysis with trade decision
        """
        if not signals:
            return self._create_neutral_analysis("No signals provided")

        # Separate buy and sell signals
        buy_signals = [s for s in signals if s.type == SignalType.BUY]
        sell_signals = [s for s in signals if s.type == SignalType.SELL]

        # Calculate confluence score
        buy_score = self._calculate_confluence_score(buy_signals)
        sell_score = self._calculate_confluence_score(sell_signals)

        logger.info(
            "[decision] Signal analysis: buy_score=%.2f, sell_score=%.2f, sources=%d",
            buy_score, sell_score, len(signals)
        )

        # Determine final signal
        if buy_score > sell_score and buy_score >= self.confluence_threshold:
            final_signal = SignalType.BUY
            final_score = buy_score
            source_signals = buy_signals
        elif sell_score > buy_score and sell_score >= self.confluence_threshold:
            final_signal = SignalType.SELL
            final_score = sell_score
            source_signals = sell_signals
        else:
            logger.info("[decision] No sufficient confluence for trade (buy=%.2f, sell=%.2f)", buy_score, sell_score)
            return self._create_neutral_analysis(f"Scores below threshold (buy={buy_score:.2f}, sell={sell_score:.2f})")

        # Calculate SL/TP
        if final_signal == SignalType.BUY:
            stop_loss = current_price - (atr * self.atr_multiplier_sl)
            take_profit = current_price + (atr * self.atr_multiplier_tp)
        else:
            stop_loss = current_price + (atr * self.atr_multiplier_sl)
            take_profit = current_price - (atr * self.atr_multiplier_tp)

        # Calculate risk/reward
        risk = abs(current_price - stop_loss)
        reward = abs(take_profit - current_price)
        rr_ratio = reward / risk if risk > 0 else 0.0

        # Determine confluence level
        if len(source_signals) >= 3:
            confluence_level = ConfluenceLevel.STRONG
        elif len(source_signals) >= 2:
            confluence_level = ConfluenceLevel.MODERATE
        else:
            confluence_level = ConfluenceLevel.WEAK

        # Calculate position size (1 lot base, adjust by confluence)
        position_size = 1.0 * (len(source_signals) / len(signals))

        return ConfluenceAnalysis(
            final_signal=final_signal,
            confluence_level=confluence_level,
            score=final_score * 100,
            contributing_signals=source_signals,
            risk_reward_ratio=rr_ratio,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            rationale=f"{len(source_signals)} sources confirmed ({', '.join(s.source for s in source_signals)})"
        )

    def validate_signal_confluence(
        self,
        signals: List[Signal]
    ) -> Tuple[bool, str]:
        """
        Quick validation if signals have sufficient confluence.

        Returns:
            Tuple of (is_valid, reason)
        """
        if not signals or len(signals) < self.min_sources:
            return False, f"Insufficient sources: {len(signals)} < {self.min_sources}"

        buy_signals = [s for s in signals if s.type == SignalType.BUY]
        sell_signals = [s for s in signals if s.type == SignalType.SELL]

        buy_score = self._calculate_confluence_score(buy_signals)
        sell_score = self._calculate_confluence_score(sell_signals)

        max_score = max(buy_score, sell_score)
        if max_score >= self.confluence_threshold:
            return True, f"Valid signal (score={max_score:.2f})"
        else:
            return False, f"Score below threshold: {max_score:.2f} < {self.confluence_threshold:.2f}"

    @staticmethod
    def _calculate_confluence_score(signals: List[Signal]) -> float:
        """
        Calculate consensus score from multiple signals.
        
        Score = average of (signal_strength * confidence) across all signals
        """
        if not signals:
            return 0.0

        scores = [
            signal.strength * signal.confidence
            for signal in signals
        ]
        return float(np.mean(scores)) if scores else 0.0

    @staticmethod
    def _create_neutral_analysis(reason: str) -> ConfluenceAnalysis:
        """Create neutral decision analysis."""
        return ConfluenceAnalysis(
            final_signal=SignalType.NEUTRAL,
            confluence_level=ConfluenceLevel.WEAK,
            score=0.0,
            contributing_signals=[],
            risk_reward_ratio=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
            rationale=reason
        )
