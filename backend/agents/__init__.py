"""
Galaxy Vast AI Trading Platform
════════════════════════════════
ماژول: Multi-Agent Architecture
"""

from .base_agent import BaseAgent, AgentVote, AgentResult
from .market_structure_agent import MarketStructureAgent
from .liquidity_agent import LiquidityAgent
from .smc_agent import SMCAgent
from .ai_prediction_agent import AIPredictionAgent
from .risk_agent import RiskAgent
from .news_agent import NewsAgent
from .execution_agent import ExecutionAgent
from .voting_engine import VotingEngine, VoteResult, TradeDecision

__all__ = [
    "BaseAgent", "AgentVote", "AgentResult",
    "MarketStructureAgent", "LiquidityAgent", "SMCAgent",
    "AIPredictionAgent", "RiskAgent", "NewsAgent", "ExecutionAgent",
    "VotingEngine", "VoteResult", "TradeDecision",
]
