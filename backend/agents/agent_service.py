"""
Galaxy Vast AI Trading Platform
Agent Service — Dependency Injection Container

Fix applied:
- CRITICAL LOGIC: AgentWeightConfig weights summed to 1.10, not 1.00
  market_structure(0.20) + liquidity(0.15) + smc(0.20) + ai_prediction(0.20)
  + risk(0.15) + news(0.10) + execution(0.10) = 1.10
  Fix: news=0.05, execution=0.05 → total = 1.00
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
    """تنظیمات وزن‌های Agentها — قابل تغییر از Dashboard.

    Total MUST equal 1.00.  Previous bug: execution+news were both 0.10
    making the total 1.10.  Fixed: news=0.05, execution=0.05.
    """
    market_structure: float = 0.20
    liquidity:        float = 0.15
    smc:              float = 0.20
    ai_prediction:    float = 0.20
    risk:             float = 0.15
    news:             float = 0.05   # was 0.10 → total was 1.10
    execution:        float = 0.05   # was 0.10 → total was 1.10

    def total(self) -> float:
        return (self.market_structure + self.liquidity + self.smc +
                self.ai_prediction + self.risk + self.news + self.execution)

    def validate(self) -> None:
        t = self.total()
        if abs(t - 1.0) > 0.01:
            raise ValueError(
                f"AgentWeightConfig weights must sum to 1.0, got {t:.4f}. "
                "Check market_structure + liquidity + smc + ai_prediction + "
                "risk + news + execution."
            )


class AgentService:
    """
    Dependency Injection Container برای Multi-Agent System.
    ساخت Agentها و VotingEngine را مدیریت می‌کند.
    """

    def __init__(
        self,
        weights: Optional[AgentWeightConfig] = None,
        min_score_threshold: float = 65.0,
        min_confidence_threshold: float = 50.0,
    ) -> None:
        self._weights = weights or AgentWeightConfig()
        self._weights.validate()   # fail fast on bad config
        self._min_score = min_score_threshold
        self._min_conf  = min_confidence_threshold
        self._engine: Optional[VotingEngine] = None
        logger.info(
            "AgentService init | weights_total=%.2f | min_score=%.1f | min_conf=%.1f",
            self._weights.total(), min_score_threshold, min_confidence_threshold,
        )

    # ────────────────────────────────────────────────────────────── #
    # Public API                                                            #
    # ────────────────────────────────────────────────────────────── #

    def get_voting_engine(self) -> VotingEngine:
        """Lazy-initialise and return the VotingEngine singleton."""
        if self._engine is None:
            self._engine = self._build_engine()
        return self._engine

    async def vote(self, context: Dict[str, Any]) -> VoteResult:
        """Run all agents and return the aggregated VoteResult."""
        return await self.get_voting_engine().vote(context)

    def update_weights(self, weight_map: Dict[str, float]) -> Dict[str, float]:
        """Update agent weights at runtime (called by Dashboard / API)."""
        for attr, val in weight_map.items():
            if hasattr(self._weights, attr):
                setattr(self._weights, attr, float(val))
        self._weights.validate()
        if self._engine is not None:
            self._engine.update_weights(weight_map)
        logger.info("AgentService weights updated: %s (total=%.2f)",
                    weight_map, self._weights.total())
        return self.get_weights()

    def get_weights(self) -> Dict[str, float]:
        """Return current weight map."""
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
        """Update minimum score threshold."""
        self._min_score = float(threshold)
        if self._engine is not None:
            self._engine.set_threshold(threshold)

    def get_agent_status(self) -> Dict[str, Any]:
        """Return per-agent enabled/weight status."""
        if self._engine is None:
            return {"status": "not_initialized"}
        return {
            a.name: {"enabled": a.enabled, "weight": a.weight}
            for a in self._engine.agents
        }

    # ────────────────────────────────────────────────────────────── #
    # Internal                                                              #
    # ────────────────────────────────────────────────────────────── #

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


# ── Module-level singleton ────────────────────────────────────────────────
_agent_service: Optional[AgentService] = None


def get_agent_service() -> AgentService:
    """Return module-level AgentService singleton."""
    global _agent_service
    if _agent_service is None:
        _agent_service = AgentService()
    return _agent_service
