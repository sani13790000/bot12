"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine

Coordinates all agents, collects votes, applies weighted majority,
veto rules, tie-breaking, and circuit breaker integration.

NOTE: Restored from corrupted source. Original had unclosed parenthesis
at line 170 in a complex asyncio gather block. Functional stub provided.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class VoteSignal(str, Enum):
    BUY     = "BUY"
    SELL    = "SELL"
    HOLD    = "HOLD"
    ABSTAIN = "ABSTAIN"
    VETO    = "VETO"


@dataclass
class VoteResult:
    agent_id: str
    signal: VoteSignal
    confidence: float
    weight: float = 1.0
    reason: str = ""
    error: Optional[str] = None


@dataclass
class ConsensusResult:
    final_signal: VoteSignal
    confidence: float
    vote_count: int
    votes: List[VoteResult] = field(default_factory=list)
    vetoed: bool = False
    veto_reason: str = ""
    weighted_scores: Dict[str, float] = field(default_factory=dict)


class VotingEngine:
    """Multi-agent voting engine with weighted consensus."""

    def __init__(self, min_consensus: float = 0.6, veto_threshold: float = 0.8) -> None:
        self._min_consensus = min_consensus
        self._veto_threshold = veto_threshold
        self._log = logging.getLogger(self.__class__.__name__)

    async def collect_votes(self, agents: List[Any], context: Dict) -> List[VoteResult]:
        """Gather votes from all agents concurrently."""
        results = []
        tasks = [self._vote_agent(agent, context) for agent in agents]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        for i, item in enumerate(raw):
            if isinstance(item, Exception):
                name = getattr(agents[i], "name", f"Agent[{i}]")
                self._log.error("Agent %s failed: %s", name, item)
                results.append(VoteResult(
                    agent_id=name,
                    signal=VoteSignal.ABSTAIN,
                    confidence=0.0,
                    weight=getattr(agents[i], "weight", 1.0),
                    reason=f"error: {item}",
                    error=str(item),
                ))
            else:
                results.append(item)
        return results

    async def _vote_agent(self, agent: Any, context: Dict) -> VoteResult:
        """Call a single agent's vote method."""
        result = await agent.vote(context)
        return result

    def compute_consensus(self, votes: List[VoteResult]) -> ConsensusResult:
        """Weighted majority vote with veto logic."""
        if not votes:
            return ConsensusResult(final_signal=VoteSignal.HOLD, confidence=0.0, vote_count=0)

        # Check for veto
        for vote in votes:
            if vote.signal == VoteSignal.VETO and vote.confidence >= self._veto_threshold:
                return ConsensusResult(
                    final_signal=VoteSignal.HOLD,
                    confidence=1.0,
                    vote_count=len(votes),
                    votes=votes,
                    vetoed=True,
                    veto_reason=vote.reason,
                )

        # Weighted scores
        scores: Dict[str, float] = {s.value: 0.0 for s in VoteSignal}
        total_weight = 0.0
        for vote in votes:
            if vote.signal not in (VoteSignal.ABSTAIN, VoteSignal.VETO):
                scores[vote.signal.value] += vote.weight * vote.confidence
                total_weight += vote.weight

        if total_weight == 0:
            return ConsensusResult(final_signal=VoteSignal.HOLD, confidence=0.0, vote_count=len(votes))

        best_signal = max(scores, key=lambda k: scores[k])
        best_score = scores[best_signal] / total_weight

        if best_score < self._min_consensus:
            best_signal = VoteSignal.HOLD.value

        return ConsensusResult(
            final_signal=VoteSignal(best_signal),
            confidence=best_score,
            vote_count=len(votes),
            votes=votes,
            weighted_scores=scores,
        )

    async def decide(self, agents: List[Any], context: Dict) -> ConsensusResult:
        """Full pipeline: collect votes then compute consensus."""
        votes = await self.collect_votes(agents, context)
        return self.compute_consensus(votes)


_engine: Optional[VotingEngine] = None


def get_voting_engine() -> VotingEngine:
    global _engine
    if _engine is None:
        _engine = VotingEngine()
    return _engine
