"""Risk Management Agent"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """Risk management configuration"""
    max_position_size: float = 10000
    max_daily_loss_pct: float = 3.0
    max_drawdown_pct: float = 8.0
    max_consecutive_losses: int = 3
    stop_loss_pct: float = 2.0
    take_profit_pct: float = 5.0


class RiskAgent(BaseAgent):
    """
    Risk management agent that validates trades and prevents
    excessive losses based on portfolio metrics.
    """
    
    def __init__(self, config: Optional[RiskConfig] = None):
        super().__init__(agent_id="risk_agent", agent_name="Risk Management")
        self.config = config or RiskConfig()
        self.enabled = True
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze risk metrics for trade decision.
        
        Args:
            market_data: Market and portfolio data
        
        Returns:
            AgentVote indicating if trade is safe
        """
        try:
            # Extract risk metrics
            portfolio_value = market_data.get("portfolio_value", 100000)
            daily_loss = market_data.get("daily_loss", 0)
            drawdown = market_data.get("drawdown_pct", 0)
            consecutive_losses = market_data.get("consecutive_losses", 0)
            position_size = market_data.get("position_size", 0)
            
            # Calculate thresholds
            daily_loss_limit = portfolio_value * (self.config.max_daily_loss_pct / 100)
            
            risk_level = "LOW"
            direction = "BUY"
            confidence = 0.9
            reason = "Risk metrics within acceptable limits"
            
            # Check risk conditions
            if daily_loss >= daily_loss_limit:
                risk_level = "CRITICAL"
                direction = "HOLD"
                confidence = 0.95
                reason = f"Daily loss limit reached ({self.config.max_daily_loss_pct}%)"
            
            elif drawdown >= self.config.max_drawdown_pct:
                risk_level = "HIGH"
                direction = "HOLD"
                confidence = 0.85
                reason = f"Drawdown limit approaching ({self.config.max_drawdown_pct}%)"
            
            elif consecutive_losses >= self.config.max_consecutive_losses:
                risk_level = "MEDIUM"
                direction = "HOLD"
                confidence = 0.75
                reason = f"Consecutive losses limit ({self.config.max_consecutive_losses})"
            
            elif position_size > self.config.max_position_size:
                risk_level = "HIGH"
                direction = "SELL"
                confidence = 0.8
                reason = f"Position size exceeds limit ({self.config.max_position_size})"
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=1.5,  # Risk agent gets high weight
                reason=reason,
                status=AgentStatus.OK,
                metadata={
                    "risk_level": risk_level,
                    "daily_loss_pct": (daily_loss / portfolio_value * 100) if portfolio_value > 0 else 0,
                    "drawdown_pct": drawdown
                }
            )
        
        except Exception as e:
            log.error(f"Risk analysis error: {e}")
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
            "max_daily_loss_pct": self.config.max_daily_loss_pct,
            "max_drawdown_pct": self.config.max_drawdown_pct,
            "status": "operational"
        }
