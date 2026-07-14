"""Smart Money Concepts (SMC) Agent"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class SMCConfig:
    """SMC configuration"""
    min_volume_ratio: float = 1.5
    min_candles_for_pattern: int = 3
    strong_signal_confidence: float = 0.85


class SMCAgent(BaseAgent):
    """
    Smart Money Concepts (SMC) agent that detects institutional
    order blocks and smart money positioning.
    """
    
    def __init__(self, config: Optional[SMCConfig] = None):
        super().__init__(agent_id="smc_agent", agent_name="SMC Agent")
        self.config = config or SMCConfig()
        self.enabled = True
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Detect SMC patterns and institutional activity.
        
        Args:
            market_data: Candle and volume data
        
        Returns:
            AgentVote with SMC signal
        """
        try:
            # Extract SMC-relevant data
            order_blocks = market_data.get("order_blocks", [])
            liquidity_levels = market_data.get("liquidity_levels", [])
            volume_spikes = market_data.get("volume_spikes", [])
            price = market_data.get("price", 0)
            
            direction = "HOLD"
            confidence = 0.5
            reason = "No strong SMC signals"
            
            # Detect order block breakouts
            if order_blocks:
                nearest_block = min(order_blocks, key=lambda x: abs(x["level"] - price))
                if nearest_block["type"] == "buy_block" and price > nearest_block["level"]:
                    direction = "BUY"
                    confidence = 0.8
                    reason = "Price above buy-side order block"
                elif nearest_block["type"] == "sell_block" and price < nearest_block["level"]:
                    direction = "SELL"
                    confidence = 0.8
                    reason = "Price below sell-side order block"
            
            # Detect liquidity sweeps
            if liquidity_levels:
                for level in liquidity_levels:
                    if abs(price - level) < 10:  # Within 10 pips
                        direction = "BUY" if level < price else "SELL"
                        confidence = 0.75
                        reason = f"Liquidity sweep at {level}"
                        break
            
            # Volume spike confirmation
            if volume_spikes and direction != "HOLD":
                confidence = min(confidence + 0.1, 1.0)
                reason += " (confirmed by volume spike)"
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=1.1,
                reason=reason,
                status=AgentStatus.OK,
                metadata={
                    "order_blocks": len(order_blocks),
                    "liquidity_levels": len(liquidity_levels),
                    "volume_spike_detected": len(volume_spikes) > 0
                }
            )
        
        except Exception as e:
            log.error(f"SMC analysis error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                direction="HOLD",
                confidence=0.0,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent": self.agent_name,
            "enabled": self.enabled,
            "min_volume_ratio": self.config.min_volume_ratio,
            "status": "operational"
        }
