"""
Galaxy Vast AI Trading Platform
Agent Service — Dependency Injection Container

Fix applied:
- CRITICAL LOGIC: AgentWeightConfig weights summed to 1.10, not 1.00
  market_structure(0.20) + liquidity(0.15) + smc(0.20) + ai_prediction(0.20)
  + risk(0.15) + news(0.10) + execution(0.10) = 1.10
  Fix: news=0.05, execution=0.05 → total = 1.00
- ARCH-10 FIX: added .agents property so deps.py can inject them into VotingEngine
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

logger = get_logger(__name__)


@dataclass
class AgentWeightConfig:
    """Weight config for agents. Total MUST equal 1.00."""
    market_structure: float = 0.20
    liquidity:        float = 0.15
    smc:              float = 0.20
    ai_prediction:    float = 0.20
    risk:             float = 0.15
    news:             float = 0.05
    execution:        float = 0.05

    def total(self) -> float:
        return (self.market_structure + self.liquidity + self.smc +
                self.ai_prediction + self.risk + self.news + self.execution)

    def validate(self) -> None:
        t = self.total()
        if abs(t - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {t:.4f}")


class AgentService:
    """DI Container for Multi-Agent System."""

    def __init__(
        self,
        weights: Optional[AgentWeightConfig] = None,
        min_score_threshold: float = 65.0,
        min_confidence_threshold: float = 50.0,
    ) -> None:
        self._weights = weights or AgentWeightConfig()
        self._weights.validate()
        self._min_score = min_score_threshold
        self._min_conf  = min_confidence_threshold
        self._engine: Optional[VotingEngine] = None
        logger.info(
            "AgentService init | weights_total=%.2f | min_score=%.1f | min_conf=%.1f",
            self._weights.total(), min_score_threshold, min_confidence_threshold,
        )

    @property
    def agents(self) -> list:
        """
        ARCH-10 FIX: expose agents list so deps.py can inject them into VotingEngine.
        Previously deps.py did getattr(agent_svc, 'agents', None) which returned None
        because AgentService had no .agents property.
        Now VotingEngine gets the real 7-agent list.
        """
        return list(self.get_voting_engine().agents)

    def get_voting_engine(self) -> VotingEngine:
        """Lazy-initialise and return the VotingEngine singleton."""
        if self._engine is None:
            self._engine = self._build_engine()
        return self._engine

    async def vote(self, context: Dict[str, Any]) -> VoteResult:
        """Run all agents and return the aggregated VoteResult."""
        return await self.get_voting_engine().vote(context)

    def update_weights(self, weight_map: Dict[str, float]) -> Dict[str, float]:
        for attr, val in weight_map.items():
            if hasattr(self._weights, attr):
                setattr(self._weights, attr, float(val))
        self._weights.validate()
        if self._engine is not None:
            self._engine.update_weights(weight_map)
        logger.info("AgentService weights updated: %s (total=%.2f)", weight_map, self._weights.total())
        return self.get_weights()

    def get_weights(self) -> Dict[str, float]:
        return {
            "market_structure": self._weights.market_structure,
            "liquidity":        self._weights.liquidity,
            "smc":              self._weights.smc,
            "ai_prediction":    self._weights.ai_prediction,
            "risk":             self._weights.risk,
            "news":             self._weights.news,
            "execution":        self._weights.execution,
            "total":            round(self._weights.total(), 4),
        }

    def set_threshold(self, threshold: float) -> None:
        self._min_score = float(threshold)
        if self._engine is not None:
            self._engine.set_threshold(threshold)

    def get_agent_status(self) -> Dict[str, Any]:
        if self._engine is None:
            return {"status": "not_initialized"}
        return {
            a.name: {"enabled": a.enabled, "weight": a.weight}
            for a in self._engine.agents
        }

    def _build_engine(self) -> VotingEngine:
        w = self._weights
        agents = [
            MarketStructureAgent(weight=w.market_structure),
            LiquidityAgent(weight=w.liquidity),
            SMCAgent(weight=w.smc),
            AIPredictionAgent(weight=w.ai_prediction),
            RiskAgent(weight=w.risk),
            NewsAgent(weight=w.news),
            ExecutionAgent(weight=w.execution),
        ]
        return VotingEngine(
            agents=agents,
            min_score_threshold=self._min_score,
            min_confidence_threshold=self._min_conf,
            run_parallel=True,
        )


_agent_service: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """Return module-level AgentService singleton."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
