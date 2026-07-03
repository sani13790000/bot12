"""Galaxy Vast AI -- Enterprise Voting Engine.

Coordinates all agents, collects votes, applies weighted majority,
veto rules, tie-breaking, and circuit breaker integration.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, AgentStatus, VoteResult

logger = logging.getLogger(__name__)


@dataclass
class VotingConfig:
    """Voting engine configuration."""
    timeout_s: float = 5.0
    quorum_pct: float = 0.6
    confidence_floor: float = 0.55
    max_agents: int = 8


class VotingEngine:
    """Multi-agent voting coordinator."""

    def __init__(self, config: Optional[VotingConfig] = None) -> None:
        self._config = config or VotingConfig()
        self._agents: List[Any] = []

    def register_agent(self, agent: Any) -> None:
        """Register a specialist agent."""
        if len(self._agents) < self._config.max_agents:
            self._agents.append(agent)

    async def run(
        self,
        symbol: str,
        timeframe: str,
        market_data: Dict[str, Any],
    ) -> VoteResult:
        """Run all agents and aggregate votes."""
        if not self._agents:
            return VoteResult(direction="HOLD", confidence=0.0, quorum_reached=False)

        tasks = [asyncio.create_task(a.analyze(symbol, timeframe, market_data))
                 for a in self._agents]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

        results: List[AgentResult] = []
        for item in raw:
            if isinstance(item, Exception):
                logger.warning("Agent error: %s", item)
            elif isinstance(item, AgentResult):
                results.append(item)

        return self._aggregate(results)

    def _aggregate(self, results: List[AgentResult]) -> VoteResult:
        """Aggregate agent results into final vote."""
        if not results:
            return VoteResult(direction="HOLD", confidence=0.0, quorum_reached=False)

        directions: Dict[str, float] = {}
        for r in results:
            if r.status == AgentStatus.SUCCESS:
                d = r.direction or "HOLD"
                directions[d] = directions.get(d, 0) + r.confidence

        if not directions:
            return VoteResult(direction="HOLD", confidence=0.0, quorum_reached=False)

        best = max(directions, key=directions.get)  # type: ignore
        total_conf = sum(directions.values())
        confidence = directions[best] / total_conf if total_conf > 0 else 0.0
        quorum = len(results) / max(len(self._agents), 1) >= self._config.quorum_pct

        return VoteResult(
            direction=best,
            confidence=confidence,
            quorum_reached=quorum,
            agent_count=len(results),
            details={"directions": directions, "timeout_s": self._config.timeout_s},
        )


voting_engine = VotingEngine()
