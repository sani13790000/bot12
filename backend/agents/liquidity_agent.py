"""Liquidity Agent - Analyze order book liquidity and volume"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class LiquidityConfig:
    """Liquidity analysis configuration"""
    min_volume_ratio: float = 1.5
    bid_ask_spread_threshold: float = 0.1  # Percentage
    volume_profile_threshold: float = 0.6
    liquidity_crisis_threshold: float = 0.3


class LiquidityMetrics:
    """Liquidity metrics"""
    bid_ask_spread: float
    bid_volume: float
    ask_volume: float
    total_volume: float
    volume_imbalance: float  # ask_volume / bid_volume
    market_depth: float
    liquidity_score: float  # 0-1


class LiquidityAgent(BaseAgent):
    """
    Analyzes market liquidity conditions.
    
    Checks:
    - Bid-ask spread
    - Order book depth
    - Volume imbalances
    - Liquidity crises
    - Slippage risk
    """
    
    def __init__(self, config: Optional[LiquidityConfig] = None):
        super().__init__(agent_id="liquidity", agent_name="Liquidity Analysis")
        self.config = config or LiquidityConfig()
        self.enabled = True
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze liquidity conditions.
        
        Args:
            market_data: Order book and volume data
        
        Returns:
            AgentVote based on liquidity analysis
        """
        try:
            # Extract liquidity indicators
            bid_ask_spread = market_data.get("bid_ask_spread", 0.05)
            bid_volume = market_data.get("bid_volume", 1000)
            ask_volume = market_data.get("ask_volume", 1000)
            total_volume = market_data.get("total_volume", 1000)
            volume_ratio = market_data.get("volume_ratio", 1.0)
            market_depth = market_data.get("market_depth", 100)
            
            # Calculate liquidity score
            liquidity_score = self._calculate_liquidity_score(
                bid_ask_spread, bid_volume, ask_volume, market_depth
            )
            
            # Detect liquidity crisis
            is_liquidity_crisis = liquidity_score < self.config.liquidity_crisis_threshold
            
            # Generate signal based on liquidity
            direction, confidence, reason = self._generate_signal(
                liquidity_score, bid_ask_spread, bid_volume, ask_volume,
                volume_ratio, is_liquidity_crisis
            )
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=1.0 if not is_liquidity_crisis else 0.5,  # Reduce weight in crisis
                reason=reason,
                status=AgentStatus.VETO if is_liquidity_crisis else AgentStatus.OK,
                metadata={
                    "liquidity_score": round(liquidity_score, 3),
                    "bid_ask_spread": round(bid_ask_spread, 5),
                    "bid_volume": bid_volume,
                    "ask_volume": ask_volume,
                    "volume_imbalance": round(ask_volume / bid_volume if bid_volume > 0 else 0, 3),
                    "market_depth": market_depth,
                    "is_crisis": is_liquidity_crisis
                }
            )
        
        except Exception as e:
            log.error(f"Liquidity analysis error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                direction="HOLD",
                confidence=0.0,
                status=AgentStatus.ERROR,
                reason=f"Analysis error: {e}",
                metadata={"error": str(e)}
            )
    
    def _calculate_liquidity_score(
        self, spread: float, bid_vol: float, ask_vol: float, depth: float
    ) -> float:
        """Calculate overall liquidity score (0-1)"""
        # Spread component (lower spread = better)
        spread_score = max(0, 1 - spread / 1.0)  # 1% spread = 0 score
        
        # Volume component
        total_vol = bid_vol + ask_vol
        volume_score = min(total_vol / 10000, 1.0)  # 10k total volume = 1.0
        
        # Depth component
        depth_score = min(depth / 1000, 1.0)  # 1000 depth = 1.0
        
        # Imbalance component
        imbalance = abs(ask_vol - bid_vol) / (total_vol + 1)
        imbalance_score = 1 - imbalance
        
        # Weighted average
        score = (
            spread_score * 0.3 +
            volume_score * 0.3 +
            depth_score * 0.2 +
            imbalance_score * 0.2
        )
        
        return max(0, min(1, score))
    
    def _generate_signal(
        self, liquidity_score: float, spread: float, bid_vol: float,
        ask_vol: float, volume_ratio: float, is_crisis: bool
    ) -> tuple:
        """Generate trading signal based on liquidity"""
        
        # Liquidity crisis - no trading
        if is_crisis:
            return "HOLD", 0.95, "Liquidity crisis detected - trading halted"
        
        # High spread warning
        if spread > self.config.bid_ask_spread_threshold:
            return "HOLD", 0.7, f"High bid-ask spread ({spread:.3%}) - slippage risk"
        
        # Good liquidity - allow trading
        if liquidity_score > 0.7:
            if ask_vol > bid_vol * self.config.min_volume_ratio:
                return "SELL", 0.6, f"Strong selling pressure (ask/bid: {ask_vol/bid_vol:.2f})"
            elif bid_vol > ask_vol * self.config.min_volume_ratio:
                return "BUY", 0.6, f"Strong buying pressure (bid/ask: {bid_vol/ask_vol:.2f})"
        
        # Acceptable liquidity
        if liquidity_score > 0.5:
            return "BUY", 0.5, f"Acceptable liquidity (score: {liquidity_score:.2f})"
        
        # Poor liquidity
        return "HOLD", 0.6, f"Limited liquidity (score: {liquidity_score:.2f})"
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent": self.agent_name,
            "enabled": self.enabled,
            "bid_ask_spread_threshold": self.config.bid_ask_spread_threshold,
            "liquidity_crisis_threshold": self.config.liquidity_crisis_threshold,
            "status": "operational"
        }
