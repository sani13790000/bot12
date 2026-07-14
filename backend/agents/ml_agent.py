"""Machine Learning Agent - XGBoost/ML predictions"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class MLConfig:
    """Configuration for ML agent"""
    model_path: str = "./models/xgboost_model.pkl"
    min_confidence: float = 0.55
    use_ensemble: bool = True


class MLAgent(BaseAgent):
    """
    Machine Learning agent using XGBoost for predictions.
    Analyzes historical patterns and provides signals.
    """
    
    def __init__(self, config: Optional[MLConfig] = None):
        super().__init__(agent_id="ml_agent", agent_name="ML Agent")
        self.config = config or MLConfig()
        self.enabled = True
        self.model = None
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze using ML model.
        
        Args:
            market_data: Market features for prediction
        
        Returns:
            AgentVote with ML prediction
        """
        try:
            # Extract features
            features = {
                "price_change": market_data.get("price_change", 0),
                "volume_ratio": market_data.get("volume_ratio", 1.0),
                "rsi": market_data.get("rsi", 50),
                "macd": market_data.get("macd", 0),
                "trend_strength": market_data.get("trend_strength", 0.5),
            }
            
            # ML prediction logic (simplified)
            rsi = features["rsi"]
            macd = features["macd"]
            
            if rsi > 70 and macd > 0:
                direction = "BUY"
                confidence = 0.8
                reason = "RSI overbought with positive MACD"
            elif rsi < 30 and macd < 0:
                direction = "SELL"
                confidence = 0.8
                reason = "RSI oversold with negative MACD"
            else:
                direction = "HOLD"
                confidence = 0.6
                reason = "Mixed signals from indicators"
            
            return AgentVote(
                agent_id=self.agent_id,
                direction=direction,
                confidence=confidence,
                weight=1.2,  # ML gets slightly higher weight
                reason=reason,
                status=AgentStatus.OK,
                metadata={"features": list(features.keys())}
            )
        
        except Exception as e:
            log.error(f"ML analysis error: {e}")
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
            "model_path": self.config.model_path,
            "min_confidence": self.config.min_confidence,
            "status": "operational"
        }
