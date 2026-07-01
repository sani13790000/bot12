"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine
Auto-repaired stub preserving interface.
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

_LOG = logging.getLogger(__name__)


class VoteAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SKIP = "SKIP"


@dataclass
class VoteResult:
    agent_id: str
    action: VoteAction
    confidence: float = 0.0
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VotingDecision:
    action: VoteAction
    confidence: float
    votes: List[VoteResult] = field(default_factory=list)
    reasoning: str = ""


class VotingEngine:
    """Multi-agent voting engine."""

    def __init__(self, agents: Optional[List[Any]] = None) -> None:
        self._agents = agents or []
        self._log = _LOG

    async def vote(self, market_data: Dict[str, Any]) -> VotingDecision:
        results: List[VoteResult] = []
        for agent in self._agents:
            try:
                result = await agent.analyze(market_data)
                if isinstance(result, VoteResult):
                    results.append(result)
            except Exception as exc:
                self._log.error("Agent vote failed: %s", exc)
        return self._aggregate(results)

    def _aggregate(self, results: List[VoteResult]) -> VotingDecision:
        if not results:
            return VotingDecision(action=VoteAction.SKIP, confidence=0.0, votes=results)
        from collections import Counter
        counts = Counter(r.action for r in results)
        best_action = counts.most_common(1)[0][0]
        relevant = [r for r in results if r.action == best_action]
        confidence = sum(r.confidence for r in relevant) / len(relevant) if relevant else 0.0
        return VotingDecision(action=best_action, confidence=confidence, votes=results)
