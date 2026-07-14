"""Execution Agent - Trade Execution & Order Management"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """Execution configuration"""
    default_lot_size: float = 0.1
    slippage_pct: float = 0.1
    order_timeout_seconds: int = 30
    use_limit_orders: bool = True


class ExecutionAgent(BaseAgent):
    """
    Execution agent that handles order placement, management,
    and execution optimization.
    """
    
    def __init__(self, config: Optional[ExecutionConfig] = None):
        super().__init__(agent_id="execution_agent", agent_name="Execution Agent")
        self.config = config or ExecutionConfig()
        self.enabled = True
        self.pending_orders: Dict[str, Any] = {}
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze execution conditions and determine if ready to execute.
        
        Args:
            market_data: Market conditions and order state
        
        Returns:
            AgentVote indicating execution readiness
        """
        try:
            bid_price = market_data.get("bid", 0)
            ask_price = market_data.get("ask", 0)
            spread = ask_price - bid_price if ask_price > bid_price else 0
            signal = market_data.get("signal", "HOLD")
            confidence_in_signal = market_data.get("confidence", 0.5)
            spread_pct = (spread / bid_price * 100) if bid_price > 0 else 0
            
            direction = "HOLD"
            confidence = 0.0
            reason = ""
            
            # Check if conditions are favorable for execution
            if signal != "HOLD" and spread_pct < 1.0:  # Acceptable spread
                direction = "BUY" if signal == "BUY" else "SELL"
                confidence = confidence_in_signal * 0.95
                reason = f"Good execution conditions, spread: {spread_pct:.2f}%"
            
            elif signal != "HOLD" and spread_pct >= 1.0:
                direction = "HOLD"
                confidence = 0.5
                reason = f"Wide spread ({spread_pct:.2f}%), waiting for better conditions"
            
            else:
                direction = "HOLD"
                confidence = 0.0
                reason = "No signal to execute"
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=1.0,
                reason=reason,
                status=AgentStatus.OK,
                metadata={
                    "spread_pct": spread_pct,
                    "bid": bid_price,
                    "ask": ask_price,
                    "pending_orders": len(self.pending_orders),
                    "lot_size": self.config.default_lot_size
                }
            )
        
        except Exception as e:
            log.error(f"Execution error: {e}")
            return AgentVote(
                agent_id=self.agent_id,
                direction="HOLD",
                confidence=0.0,
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )
    
    async def execute_trade(self, symbol: str, direction: str, 
                           lot_size: Optional[float] = None) -> Dict[str, Any]:
        """
        Execute a trade.
        
        Args:
            symbol: Trading symbol
            direction: BUY or SELL
            lot_size: Trade size
        
        Returns:
            Execution result
        """
        try:
            size = lot_size or self.config.default_lot_size
            
            order = {
                "symbol": symbol,
                "direction": direction,
                "lot_size": size,
                "status": "pending",
                "timestamp": 0  # Would use time.time()
            }
            
            self.pending_orders[f"{symbol}_{len(self.pending_orders)}"] = order
            
            log.info(f"Order executed: {symbol} {direction} {size}L")
            return {"success": True, "order": order}
        
        except Exception as e:
            log.error(f"Trade execution failed: {e}")
            return {"success": False, "error": str(e)}
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent": self.agent_name,
            "enabled": self.enabled,
            "default_lot_size": self.config.default_lot_size,
            "pending_orders": len(self.pending_orders),
            "status": "operational"
        }
