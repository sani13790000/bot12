"""Market Structure Agent - Analyze market regime and structure"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class MarketStructureConfig:
    """Market structure analysis configuration"""
    trend_strength_threshold: float = 0.6
    volatility_threshold: float = 2.0  # Standard deviations
    regime_change_sensitivity: float = 0.7


class MarketStructure:
    """Represents market structure analysis"""
    trend: str  # "UP", "DOWN", "SIDEWAYS"
    strength: float  # 0-1
    volatility: float
    regime: str  # "TRENDING", "MEAN_REVERT", "CHOPPY"
    support_level: float
    resistance_level: float


class MarketStructureAgent(BaseAgent):
    """
    Analyzes market structure and regime.
    
    Identifies:
    - Trend strength and direction
    - Support/resistance levels
    - Market regime (trending vs mean-reversion)
    - Volatility environment
    - Breakout opportunities
    """
    
    def __init__(self, config: Optional[MarketStructureConfig] = None):
        super().__init__(agent_id="market_structure", agent_name="Market Structure")
        self.config = config or MarketStructureConfig()
        self.enabled = True
        self.support_level = 0.0
        self.resistance_level = 0.0
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze market structure.
        
        Args:
            market_data: OHLCV and structural data
        
        Returns:
            AgentVote based on market structure analysis
        """
        try:
            # Extract market structure indicators
            trend = market_data.get("trend", "SIDEWAYS")
            trend_strength = market_data.get("trend_strength", 0.5)
            volatility = market_data.get("volatility", 1.0)
            support = market_data.get("support_level", market_data.get("low", 0))
            resistance = market_data.get("resistance_level", market_data.get("high", 0))
            price = market_data.get("price", 0)
            
            self.support_level = support
            self.resistance_level = resistance
            
            # Analyze market regime
            regime = self._identify_regime(trend, trend_strength, volatility)
            
            # Generate signal based on structure
            direction, confidence, reason = self._generate_signal(
                trend, trend_strength, regime, price, support, resistance, volatility
            )
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=1.1,
                reason=reason,
                status=AgentStatus.OK,
                metadata={
                    "trend": trend,
                    "trend_strength": round(trend_strength, 3),
                    "regime": regime,
                    "volatility": round(volatility, 3),
                    "support": round(support, 5),
                    "resistance": round(resistance, 5)
                }
            )
        
        except Exception as e:
            log.error(f"Market structure analysis error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                direction="HOLD",
                confidence=0.0,
                status=AgentStatus.ERROR,
                reason=f"Analysis error: {e}",
                metadata={"error": str(e)}
            )
    
    def _identify_regime(self, trend: str, strength: float, volatility: float) -> str:
        """Identify market regime"""
        if strength > self.config.trend_strength_threshold:
            return "TRENDING"
        elif volatility > self.config.volatility_threshold:
            return "CHOPPY"
        else:
            return "MEAN_REVERT"
    
    def _generate_signal(
        self, trend: str, strength: float, regime: str, price: float,
        support: float, resistance: float, volatility: float
    ) -> tuple:
        """Generate trading signal from market structure"""
        
        if regime == "TRENDING" and strength > 0.7:
            if trend == "UP":
                return "BUY", min(strength, 0.95), f"Strong uptrend ({strength:.1%})"
            elif trend == "DOWN":
                return "SELL", min(strength, 0.95), f"Strong downtrend ({strength:.1%})"
        
        if regime == "CHOPPY":
            # Mean reversion in choppy markets
            price_range = resistance - support
            if price_range > 0:
                price_position = (price - support) / price_range
                if price_position > 0.8:
                    return "SELL", 0.7, "Price near resistance in choppy market"
                elif price_position < 0.2:
                    return "BUY", 0.7, "Price near support in choppy market"
        
        if regime == "MEAN_REVERT":
            # Support/resistance bounces
            if abs(price - support) < price_range * 0.05:
                return "BUY", 0.75, "Price at support level"
            if abs(price - resistance) < price_range * 0.05:
                return "SELL", 0.75, "Price at resistance level"
        
        return "HOLD", 0.5, f"Neutral structure ({regime})"
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent": self.agent_name,
            "enabled": self.enabled,
            "support": self.support_level,
            "resistance": self.resistance_level,
            "status": "operational"
        }
