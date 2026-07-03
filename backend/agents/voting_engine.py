"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine

Coordinates all agents, collects votes, applies weighted majority,
veto rules, tie-breaking, and circuit breaker integration.
FIX: Import AgentStatus, AgentResult, VoteResult from base_agent (not core modules).
MS-4: Sequential fallback when gather fails.
MS-5: Per-agent error isolation (gather return_exceptions=True).
Note: results lists are bounded (one entry per agent, max ~8).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base_agent import (
    AgentResult,
    AgentStatus,
    AgentVote,
    BaseAgent,
    VoteResult,
    VoteSignal,
)


_LOG = logging.getLogger(__name__)
_RISK_AGENT_NAME = "risk_agent"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class VotingConfig:
    timeout_s:           float = _DEFAULT_TIMEOUT
    min_agents:           int   = 3
    quorum_pct:          float = 0.6
    confidence_floor:    float = 55.0
    sequential_fallback: bool  = True


@dataclass
class FinalVote:
    """Aggregated vote result from all agents."""
    signal:       VoteSignal
    confidence:   float
    reason:       str
    votes:        List[VoteResult] = field(default_factory=list)
    blocked:      bool = False
    block_reason: str  = ""

    @property
    def approved(self) -> bool:
        return not self.blocked and self.signal in (VoteSignal.BUY, VoteSignal.SELL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal":       self.signal.value,
            "confidence":   round(self.confidence, 4),
            "reason":       self.reason,
            "approved":     self.approved,
            "blocked":      self.blocked,
            "block_reason": self.block_reason,
            "votes":        [v.__dict__ if hasattr(v, '__dict__') else str(v) for v in self.votes],
        }


class VotingEngine:
    """
    Multi-agent voting coordinator.

    Flow:
        1. Broadcast context to all agents concurrently (asyncio.gather).
        2. Apply RISK veto — if risk_agent vetoes, block immediately.
        3. Weighted majority vote with quorum check.
        4. Confidence floor filter.
        5. Return FinalVote.

    Fallback (MS-4):
        If gather() raises (e.g. timeout), fall back to sequential
        agent calls so a single bad agent does not kill the whole cycle.
    """

    def __init__(self, config: Optional[VotingConfig] = None) -> None:
        self._cfg = config or VotingConfig()
        self._log = _LOG

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def vote(
        self,
        agents:  List[BaseAgent],
        context: Dict[str, Any],
    ) -> FinalVote:
        """Run a full voting cycle and return the aggregated decision."""
        if not agents:
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason="no agents registered",
            )

        # 1. Collect votes
        raw_votes = await self._gather_votes(agents, context)

        # 2. Risk veto
        veto = self._check_risk_veto(raw_votes)
        if veto:
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason=f"risk_agent veto: {veto}",
                votes=raw_votes,
                blocked=True,
                block_reason=veto,
            )

        # 3. Quorum check
        active = [v for v in raw_votes if v.signal != VoteSignal.ABSTAIN]
        if len(active) < self._cfg.min_agents:
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason=f"quorum not met: {len(active)}/{self._cfg.min_agents}",
                votes=raw_votes,
            )

        # 4. Weighted tally
        return self._tally(raw_votes)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _gather_votes(
        self,
        agents:  List[BaseAgent],
        context: Dict[str, Any],
    ) -> List[VoteResult]:
        """Gather votes from all agents with error isolation (MS-5)."""
        try:
            raw = await asyncio.wait_for(
                asyncio.gather(
                    *[a.vote(context) for a in agents],
                    return_exceptions=True,
                ),
                timeout=self._cfg.timeout_s,
            )
        except asyncio.TimeoutError:
            self._log.warning("VotingEngine: gather timed out, trying sequential fallback")
            if self._cfg.sequential_fallback:
                return await self._run_sequential_safe(agents, context)
            return []

        return self._process_raw(raw, agents)

    def _process_raw(
        self,
        raw:    List[Any],
        agents: List[BaseAgent],
    ) -> List[VoteResult]:
        """Convert gather() results into VoteResult list (MS-5)."""
        results: List[VoteResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = getattr(agents[i], "agent_id",
                               getattr(agents[i], "name", f"Agent[{i}]"))
                self._log.error("MS-5 gather fallback for %s: %s", name, item)
                results.append(
                    VoteResult(
                        agent_id=name,
                        signal=VoteSignal.ABSTAIN,
                        confidence=0.0,
                        weight=getattr(agents[i], "weight", 1.0),
                        reason=f"error: {item}",
                        error=str(item),
                    )
                )
            else:
                results.append(item)
        return results

    async def _run_sequential_safe(
        self, agents: List[Any], context: Dict[str, Any]
    ) -> List[VoteResult]:
        """MS-4: sequential fallback when gather fails."""
        results: List[VoteResult] = []
        for agent in agents:
            try:
                vote = await asyncio.wait_for(agent.vote(context), timeout=self._cfg.timeout_s)
                results.append(vote)
            except Exception as exc:
                name = getattr(agent, "agent_id", getattr(agent, "name", str(agent)))
                self._log.error("Sequential fallback error for %s: %s", name, exc)
                results.append(VoteResult(
                    agent_id=name,
                    signal=VoteSignal.ABSTAIN,
                    confidence=0.0,
                    weight=getattr(agent, "weight", 1.0),
                    reason=f"sequential error: {exc}",
                    error=str(exc),
                ))
        return results

    def _check_risk_veto(self, votes: List[VoteResult]) -> Optional[str]:
        """Return veto reason string if risk_agent issued VETO, else None."""
        for v in votes:
            if v.agent_id == _RISK_AGENT_NAME and v.signal == VoteSignal.VETO:
                return v.reason or "risk veto"
        return None

    def _tally(self, votes: List[VoteResult]) -> FinalVote:
        """Weighted majority tally with confidence floor."""
        buy_w = sell_w = abs_w = 0.0
        total_w = 0.0
        weighted_conf = 0.0

        for v in votes:
            w = max(0.0, v.weight)
            total_w += w
            if v.signal == VoteSignal.BUY:
                buy_w += w
            elif v.signal == VoteSignal.SELL:
                sell_w += w
            else:
                abs_w += w
            weighted_conf += v.confidence * w

        if total_w == 0:
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason="zero total weight",
                votes=votes,
            )

        avg_conf = weighted_conf / total_w

        if avg_conf < self._cfg.confidence_floor:
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=avg_conf,
                reason=f"confidence below floor ({avg_conf:.1f} < {self._cfg.confidence_floor})",
                votes=votes,
            )

        if buy_w / total_w >= self._cfg.quorum_pct:
            return FinalVote(
                signal=VoteSignal.BUY,
                confidence=avg_conf,
                reason=f"BUY quorum {buy_w/total_w:.0%}",
                votes=votes,
            )
        if sell_w / total_w >= self._cfg.quorum_pct:
            return FinalVote(
                signal=VoteSignal.SELL,
                confidence=avg_conf,
                reason=f"SELL quorum {sell_w/total_w:.0%}",
                votes=votes,
            )

        return FinalVote(
            signal=VoteSignal.ABSTAIN,
            confidence=avg_conf,
            reason=f"no quorum (buy={buy_w/total_w:.0%} sell={sell_w/total_w:.0%})",
            votes=votes,
        )


# Module-level singleton
voting_engine = VotingEngine()
