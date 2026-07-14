"""Security AI Agent - Fraud Detection & Account Security"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

from .base_agent import BaseAgent, AgentVote, AgentStatus

log = logging.getLogger(__name__)


@dataclass
class SecurityConfig:
    """Security analysis configuration"""
    anomaly_threshold: float = 0.7
    check_ip_changes: bool = True
    check_unusual_trades: bool = True
    check_rapid_orders: bool = True
    suspicious_pattern_threshold: float = 0.8


class SecurityAIAgent(BaseAgent):
    """
    Security-focused AI agent that detects:
    - Fraudulent transactions
    - Unusual trading patterns
    - Account security threats
    - Anomalous behavior
    """
    
    def __init__(self, config: Optional[SecurityConfig] = None):
        super().__init__(agent_id="security_ai", agent_name="Security AI")
        self.config = config or SecurityConfig()
        self.enabled = True
        self.has_veto = True  # Security can veto trades
    
    async def analyze(self, market_data: Dict[str, Any]) -> AgentVote:
        """
        Analyze for security threats and fraud patterns.
        
        Args:
            market_data: Market and account data
        
        Returns:
            AgentVote - VETO if threat detected, otherwise BUY/SELL
        """
        try:
            # Extract security indicators
            trade_frequency = market_data.get("trade_frequency", 0)
            order_size_deviation = market_data.get("order_size_deviation", 0)
            ip_changed = market_data.get("ip_changed", False)
            unusual_pattern_score = market_data.get("unusual_pattern_score", 0)
            
            # Check for security threats
            threat_level = 0.0
            threat_reasons = []
            
            # Rapid order placement (DDoS-like behavior)
            if trade_frequency > 100:  # More than 100 orders per minute
                threat_level += 0.3
                threat_reasons.append("Rapid order placement detected")
            
            # Unusual order size deviations
            if order_size_deviation > 3.0:  # 3 standard deviations
                threat_level += 0.25
                threat_reasons.append("Unusual order size patterns")
            
            # IP address change
            if ip_changed:
                threat_level += 0.15
                threat_reasons.append("IP address changed")
            
            # Anomalous behavior patterns
            if unusual_pattern_score > self.config.anomaly_threshold:
                threat_level += 0.3
                threat_reasons.append("Anomalous behavior detected")
            
            # Determine response
            if threat_level > self.config.suspicious_pattern_threshold:
                # VETO - block all trading
                return AgentVote(
                    agent_id=self.agent_id,
                    direction="HOLD",
                    confidence=threat_level,
                    weight=2.0,  # High weight for security
                    reason=f"Security threat detected: {'; '.join(threat_reasons)}",
                    status=AgentStatus.VETO,
                    metadata={"threat_level": threat_level, "threat_reasons": threat_reasons}
                )
            elif threat_level > 0.5:
                # Warning - switch to HOLD (conservative)
                return AgentVote(
                    agent_id=self.agent_id,
                    direction="HOLD",
                    confidence=0.8,
                    weight=1.5,
                    reason=f"Security concerns: {'; '.join(threat_reasons)}",
                    status=AgentStatus.OK,
                    metadata={"threat_level": threat_level}
                )
            else:
                # No threats - allow trading
                return AgentVote(
                    agent_id=self.agent_id,
                    direction="BUY",  # Allow other agents' signals
                    confidence=0.9,
                    weight=1.0,
                    reason="Account security normal",
                    status=AgentStatus.OK,
                    metadata={"threat_level": threat_level}
                )
        
        except Exception as e:
            log.error(f"Security analysis error: {e}")
            # Default to HOLD on error (safe)
            return AgentVote(
                agent_id=self.agent_id,
                direction="HOLD",
                confidence=0.5,
                weight=1.0,
                reason=f"Security check error: {e}",
                status=AgentStatus.ERROR,
                metadata={"error": str(e)}
            )
    
    def get_status(self) -> Dict[str, Any]:
        """Get agent status"""
        return {
            "agent": self.agent_name,
            "enabled": self.enabled,
            "has_veto": self.has_veto,
            "anomaly_threshold": self.config.anomaly_threshold,
            "status": "operational"
        }
