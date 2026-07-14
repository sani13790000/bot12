"""
Decision Engine - Signal Confirmation and Trade Decision Logic.

Validates signals from various sources and makes final trading decisions.
Ensures signal confluence before issuing trade commands.
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """Signal types from different engines."""
    SMC_BULLISH = "smc_bullish"
    SMC_BEARISH = "smc_bearish"
    PRICE_ACTION_BULLISH = "price_action_bullish"
    PRICE_ACTION_BEARISH = "price_action_bearish"
    ML_BULLISH = "ml_bullish"
    ML_BEARISH = "ml_bearish"
    NEWS_BULLISH = "news_bullish"
    NEWS_BEARISH = "news_bearish"


class ConfidenceLevel(Enum):
    """Signal confidence levels."""
    LOW = 0.3
    MEDIUM = 0.6
    HIGH = 0.8
    VERY_HIGH = 0.95


@dataclass
class Signal:
    """Input signal from an analysis engine."""
    type: SignalType
    confidence: float  # 0-1
    source: str  # 'smc', 'price_action', 'ml', 'news', etc.
    timestamp: datetime
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class TradeDecision:
    """Final trade decision."""
    direction: str  # 'BUY', 'SELL', or 'HOLD'
    confidence: float  # 0-1, decision confidence
    entry_price: Optional[float]
    stop_loss: Optional[float]
    take_profit: Optional[float]
    signals_used: List[Signal]
    reason: str  # Human-readable reason
    timestamp: datetime
    risk_reward_ratio: Optional[float] = None


class DecisionEngine:
    """
    Consolidates signals from multiple sources and makes trade decisions.
    
    Implements confluence detection: a signal is more reliable when multiple
    engines agree on the same direction.
    """
    
    def __init__(
        self,
        min_confluence: int = 2,  # Minimum signals to trigger trade
        confluence_weight: float = 0.3  # Weight boost for confluent signals
    ):
        """
        Initialize Decision Engine.
        
        Args:
            min_confluence: Minimum number of agreeing signals for trade
            confluence_weight: Confidence boost for each additional confluent signal
        """
        self.min_confluence = min_confluence
        self.confluence_weight = confluence_weight
        self.signal_history: List[Signal] = []
        self.decision_history: List[TradeDecision] = []
    
    def add_signal(self, signal: Signal) -> None:
        """Record an incoming signal."""
        self.signal_history.append(signal)
        logger.info(
            f"Signal received: {signal.type.value} from {signal.source} "
            f"(confidence: {signal.confidence:.2f})"
        )
    
    def make_decision(
        self,
        signals: List[Signal],
        current_price: float,
        atr: Optional[float] = None,
        recent_support: Optional[float] = None,
        recent_resistance: Optional[float] = None
    ) -> TradeDecision:
        """
        Make a trade decision based on multiple signals.
        
        Args:
            signals: List of signals from different sources
            current_price: Current market price
            atr: Average True Range for sizing stops/targets
            recent_support: Nearest support level
            recent_resistance: Nearest resistance level
        
        Returns:
            TradeDecision with BUY, SELL, or HOLD
        """
        try:
            if not signals:
                return TradeDecision(
                    direction='HOLD',
                    confidence=0.0,
                    entry_price=None,
                    stop_loss=None,
                    take_profit=None,
                    signals_used=[],
                    reason='No signals provided',
                    timestamp=datetime.now()
                )
            
            # Count bullish vs bearish signals
            bullish_signals, bearish_signals = self._split_signals(signals)
            
            # Calculate confidence
            bullish_conf = self._calculate_confluence_confidence(bullish_signals)
            bearish_conf = self._calculate_confluence_confidence(bearish_signals)
            
            # Determine direction
            if bullish_conf > bearish_conf and bullish_conf >= self._min_confidence_threshold():
                decision = self._create_buy_decision(
                    bullish_signals, bullish_conf, current_price, atr, recent_support, recent_resistance
                )
            elif bearish_conf > bullish_conf and bearish_conf >= self._min_confidence_threshold():
                decision = self._create_sell_decision(
                    bearish_signals, bearish_conf, current_price, atr, recent_support, recent_resistance
                )
            else:
                decision = TradeDecision(
                    direction='HOLD',
                    confidence=max(bullish_conf, bearish_conf),
                    entry_price=None,
                    stop_loss=None,
                    take_profit=None,
                    signals_used=signals,
                    reason=f'Insufficient confluence: Bullish={bullish_conf:.2f}, Bearish={bearish_conf:.2f}',
                    timestamp=datetime.now()
                )
            
            self.decision_history.append(decision)
            logger.info(f"Decision made: {decision.direction} (confidence: {decision.confidence:.2f})")
            return decision
        
        except Exception as e:
            logger.error(f"Error making decision: {e}")
            return TradeDecision(
                direction='HOLD',
                confidence=0.0,
                entry_price=None,
                stop_loss=None,
                take_profit=None,
                signals_used=signals,
                reason=f'Error: {str(e)}',
                timestamp=datetime.now()
            )
    
    def _split_signals(self, signals: List[Signal]) -> Tuple[List[Signal], List[Signal]]:
        """Separate signals into bullish and bearish."""
        bullish = [s for s in signals if 'bullish' in s.type.value.lower()]
        bearish = [s for s in signals if 'bearish' in s.type.value.lower()]
        return bullish, bearish
    
    def _calculate_confluence_confidence(self, signals: List[Signal]) -> float:
        """
        Calculate confidence based on signal confluence.
        
        More signals in same direction = higher confidence.
        Higher individual signal confidence = higher overall confidence.
        """
        if not signals:
            return 0.0
        
        # Base confidence from average signal confidence
        base_conf = sum(s.confidence for s in signals) / len(signals)
        
        # Confluence boost: each signal after the first adds weight
        confluence_count = max(0, len(signals) - 1)
        confluence_boost = min(
            0.3,  # Cap boost at 0.3
            confluence_count * self.confluence_weight
        )
        
        final_conf = min(1.0, base_conf + confluence_boost)
        return final_conf
    
    def _min_confidence_threshold(self) -> float:
        """Minimum confidence required to issue trade."""
        return 0.55  # 55% confidence minimum
    
    def _create_buy_decision(
        self,
        signals: List[Signal],
        confidence: float,
        current_price: float,
        atr: Optional[float],
        recent_support: Optional[float],
        recent_resistance: Optional[float]
    ) -> TradeDecision:
        """Create a BUY decision with entry, SL, TP."""
        entry_price = current_price
        
        # Stop loss: below recent support or ATR
        if recent_support:
            stop_loss = recent_support - (atr or 0.0010 * current_price)
        else:
            stop_loss = current_price - (atr or 0.0010 * current_price)
        
        # Take profit: 2:1 risk/reward ratio
        risk = entry_price - stop_loss
        take_profit = entry_price + (risk * 2)
        
        risk_reward = risk / (stop_loss) if stop_loss != 0 else None
        
        return TradeDecision(
            direction='BUY',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signals_used=signals,
            reason=f'Bullish confluence: {len(signals)} signals, avg confidence {confidence:.2f}',
            timestamp=datetime.now(),
            risk_reward_ratio=risk_reward
        )
    
    def _create_sell_decision(
        self,
        signals: List[Signal],
        confidence: float,
        current_price: float,
        atr: Optional[float],
        recent_support: Optional[float],
        recent_resistance: Optional[float]
    ) -> TradeDecision:
        """Create a SELL decision with entry, SL, TP."""
        entry_price = current_price
        
        # Stop loss: above recent resistance or ATR
        if recent_resistance:
            stop_loss = recent_resistance + (atr or 0.0010 * current_price)
        else:
            stop_loss = current_price + (atr or 0.0010 * current_price)
        
        # Take profit: 2:1 risk/reward ratio
        risk = stop_loss - entry_price
        take_profit = entry_price - (risk * 2)
        
        risk_reward = risk / entry_price if entry_price != 0 else None
        
        return TradeDecision(
            direction='SELL',
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signals_used=signals,
            reason=f'Bearish confluence: {len(signals)} signals, avg confidence {confidence:.2f}',
            timestamp=datetime.now(),
            risk_reward_ratio=risk_reward
        )
    
    def validate_signal_confluence(
        self,
        signals: List[Signal],
        required_sources: List[str] = None
    ) -> Tuple[bool, str]:
        """
        Validate that signals have proper confluence.
        
        Args:
            signals: List of signals to validate
            required_sources: If specified, all these sources must be present
        
        Returns:
            Tuple of (is_valid, reason)
        """
        if not signals:
            return False, "No signals provided"
        
        if len(signals) < self.min_confluence:
            return False, f"Insufficient signals: {len(signals)} < {self.min_confluence}"
        
        sources = set(s.source for s in signals)
        if required_sources and not all(s in sources for s in required_sources):
            missing = set(required_sources) - sources
            return False, f"Missing required sources: {missing}"
        
        # Check for directional agreement
        bullish = sum(1 for s in signals if 'bullish' in s.type.value.lower())
        bearish = sum(1 for s in signals if 'bearish' in s.type.value.lower())
        
        if bullish > 0 and bearish > 0:
            logger.warning(f"Mixed signals: {bullish} bullish, {bearish} bearish")
        
        # All confidence levels above minimum
        min_conf = min(s.confidence for s in signals)
        if min_conf < 0.3:
            return False, f"Low confidence signal: {min_conf:.2f} < 0.3"
        
        return True, "Signals valid"
    
    def get_last_decision(self) -> Optional[TradeDecision]:
        """Get the most recent trade decision."""
        return self.decision_history[-1] if self.decision_history else None
    
    def clear_history(self):
        """Clear signal and decision history."""
        self.signal_history.clear()
        self.decision_history.clear()
        logger.info("DecisionEngine history cleared")
