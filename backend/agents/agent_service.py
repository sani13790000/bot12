"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Agent Service — Dependency Injection Container
ساخت و مدیریت تمام Agentها و VotingEngine
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend.core.config import settings
from backend.core.logger import get_logger

from .ai_prediction_agent import AIPredictionAgent
from .execution_agent import ExecutionAgent
from .liquidity_agent import LiquidityAgent
from .market_structure_agent import MarketStructureAgent
from .news_agent import NewsAgent
from .risk_agent import RiskAgent
from .smc_agent import SMCAgent
from .voting_engine import VoteResult, VotingEngine


@dataclass
class AgentWeightConfig:
    """تنظیم وزن‌های Agentها — قابل تغییر از Dashboard."""
    market_structure: float = 0.20
    liquidity:        float = 0.15
    smc:              float = 0.20
    ai_prediction:    float = 0.20
    risk:             float = 0.15
    news:             float = 0.10
    execution:        float = 0.10

    def total(self) -> float:
        return (self.market_structure + self.liquidity + self.smc +
                self.ai_prediction + self.risk + self.news + self.execution)


class AgentService:
    """
    Dependency Injection Container برای Multi-Agent System.

    استفاده:
        service = AgentService()
        result  = await service.evaluate(context)
        print(result.decision)  # BUY / SELL / NO_TRADE / BLOCKED
    """

    def __init__(
        self,
        weights: Optional[AgentWeightConfig] = None,
        min_score_threshold: float = 65.0,
        min_confidence_threshold: float = 50.0,
        block_on_news: bool = False,
        news_minutes_before: int = 30,
    ) -> None:
        self._logger  = get_logger("agents.service")
        self._weights = weights or AgentWeightConfig()

        # ساخت همه Agentها
        self._agents = [
            MarketStructureAgent(weight=self._weights.market_structure),
            LiquidityAgent(      weight=self._weights.liquidity),
            SMCAgent(            weight=self._weights.smc),
            AIPredictionAgent(   weight=self._weights.ai_prediction),
            RiskAgent(
                weight=self._weights.risk,
                max_portfolio_risk=getattr(settings, "MAX_PORTFOLIO_RISK_PERCENT", 5.0),
                max_spread_ratio=getattr(settings, "MAX_SPREAD_RATIO", 2.0),
            ),
            NewsAgent(
                weight=self._weights.news,
                block_on_high_impact=block_on_news,
                minutes_before=news_minutes_before,
            ),
            ExecutionAgent(weight=self._weights.execution),
        ]

        # ساخت VotingEngine
        self._voting_engine = VotingEngine(
            agents=self._agents,
            min_score_threshold=min_score_threshold,
            min_confidence_threshold=min_confidence_threshold,
            run_parallel=True,
        )

        self._logger.info(
            f"AgentService initialized — {len(self._agents)} agents | "
            f"threshold={min_score_threshold}"
        )

    async def evaluate(self, context: Dict[str, Any]) -> VoteResult:
        """ارزیابی کامل توسط همه Agentها."""
        self._logger.debug(f"Evaluating context for {context.get('symbol', '?')} {context.get('direction', '?')}")
        return await self._voting_engine.vote(context)

    def update_weights(self, weight_map: Dict[str, float]) -> None:
        """بروزرسانی وزن‌ها از WeightAdjuster یا Dashboard."""
        self._voting_engine.update_weights(weight_map)
        self._logger.info(f"Weights updated: {weight_map}")

    def set_threshold(self, threshold: float) -> None:
        self._voting_engine.set_threshold(threshold)
        self._logger.info(f"Threshold updated: {threshold}")

    def enable_agent(self, name: str) -> None:
        self._voting_engine.enable_agent(name)

    def disable_agent(self, name: str) -> None:
        self._voting_engine.disable_agent(name)

    def get_agent_weights(self) -> Dict[str, float]:
        return self._voting_engine.get_weights()

    def get_agent_names(self) -> list:
        return [a.name for a in self._agents]

    @property
    def voting_engine(self) -> VotingEngine:
        return self._voting_engine


# ── Singleton ─────────────────────────────────────────────────
_agent_service_instance: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """FastAPI Dependency Injection."""
    global _agent_service_instance
    if _agent_service_instance is None:
        _agent_service_instance = AgentService()
    return _agent_service_instance


def reset_agent_service() -> None:
    """برای تست‌ها — reset singleton."""
    global _agent_service_instance
    _agent_service_instance = None
