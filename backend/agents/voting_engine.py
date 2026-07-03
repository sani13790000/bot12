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
from typing import Dict, List, Optional, Sequence

from ..circuit_breaker import CircuitBreaker, BreakerState
from .base_agent import BaseAgent, AgentStatus, AgentResult, VoteResult, VoteSignal

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Veto rules
# ---------------------------------------------------------------------------

class VetoRule:
    """Single veto rule that can block a trade."""

    def __init__(self, name: str, condition, reason: str) -> None:
        self.name      = name
        self.condition = condition
        self.reason    = reason

    def applies(self, results: List[VoteResult]) -> bool:
        try:
            return bool(self.condition(results))
        except Exception as exc:
            logger.error("VetoRule %s error: %s", self.name, exc)
            return False


DEFAULT_VETO_RULES: List[VetoRule] = [
    VetoRule(
        name="risk_veto",
        condition=lambda rs: any(
            r.agent_id == "risk_agent" and r.signal == VoteSignal.VETO
            for r in rs
        ),
        reason="Risk agent vetoed the trade",
    ),
    VetoRule(
        name="kill_switch_veto",
        condition=lambda rs: any(
            r.agent_id == "kill_switch" and r.signal == VoteSignal.VETO
            for r in rs
        ),
        reason="Kill switch is active",
    ),
]


# ---------------------------------------------------------------------------
# VotingEngine
# ---------------------------------------------------------------------------

class VotingEngine:
    """
    Orchestrates all registered agents, collects their VoteResult objects,
    applies veto rules, weighted majority voting, and returns a final decision.

    Circuit breaker: if >= BREAKER_THRESHOLD agents fail consecutively,
    the engine opens and returns ABSTAIN until agents recover.
    """

    BREAKER_THRESHOLD = 3
    GATHER_TIMEOUT    = 10.0   # seconds

    def __init__(
        self,
        agents:      List[BaseAgent],
        veto_rules:  Optional[List[VetoRule]] = None,
        breaker:     Optional[CircuitBreaker] = None,
    ) -> None:
        self._agents     = agents
        self._veto_rules = veto_rules if veto_rules is not None else DEFAULT_VETO_RULES
        self._breaker    = breaker or CircuitBreaker(threshold=self.BREAKER_THRESHOLD)
        self._log        = logging.getLogger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def decide(self, market_data: dict) -> AgentResult:
        """
        Gather votes from all agents, apply veto rules, and return
        a weighted majority AgentResult.

        Returns ABSTAIN if circuit breaker is open.
        """
        if self._breaker.state == BreakerState.OPEN:
            self._log.warning("Circuit breaker OPEN — returning ABSTAIN")
            return self._abstain_result("circuit_breaker_open")

        votes = await self._gather_votes(market_data)

        # Apply veto rules before counting votes
        for rule in self._veto_rules:
            if rule.applies(votes):
                self._log.info("VETO applied: %s — %s", rule.name, rule.reason)
                return self._abstain_result(rule.reason)

        return self._tally(votes)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _gather_votes(self, market_data: dict) -> List[VoteResult]:
        """Collect votes from all agents with per-agent error isolation (MS-5)."""
        agents  = self._agents
        tasks   = [agent.vote(market_data) for agent in agents]

        try:
            raw = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.GATHER_TIMEOUT,
            )
        except asyncio.TimeoutError:
            self._log.error("gather timeout after %.1fs — falling back to sequential", self.GATHER_TIMEOUT)
            raw = await self._sequential_fallback(agents, market_data)

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
                    ))
            else:
                results.append(item)
        return results

    async def _sequential_fallback(self, agents, market_data):
        """MS-4: Run agents one by one when gather fails."""
        results = []
        for agent in agents:
            try:
                results.append(await asyncio.wait_for(agent.vote(market_data), timeout=3.0))
            except Exception as exc:
                results.append(exc)
        return results

    def _tally(self, votes: List[VoteResult]) -> AgentResult:
        """Weighted majority vote: BUY vs SELL vs ABSTAIN."""
        weights: Dict[VoteSignal, float] = {
            VoteSignal.BUY:     0.0,
            VoteSignal.SELL:    0.0,
            VoteSignal.ABSTAIN: 0.0,
        }
        total_weight = 0.0

        for v in votes:
            w = v.weight * v.confidence
            weights[v.signal] = weights.get(v.signal, 0.0) + w
            total_weight += w

        if total_weight == 0:
            return self._abstain_result("no valid votes")

        # Normalize
        for sig in weights:
            weights[sig] /= total_weight

        best_signal = max(weights, key=weights.__getitem__)
        best_conf   = weights[best_signal]

        # Require minimum confidence to act
        if best_conf < 0.55 or best_signal == VoteSignal.ABSTAIN:
            return self._abstain_result(f"low confidence {best_conf:.2%}")

        self._log.info(
            "VOTE RESULT | signal=%s | confidence=%.2f | votes=%d",
            best_signal.value, best_conf, len(votes)
        )
        return AgentResult(
            signal     = best_signal,
            confidence = best_conf,
            reason     = f"weighted majority {best_conf:.2%}",
            votes      = votes,
        )

    @staticmethod
    def _abstain_result(reason: str) -> AgentResult:
        return AgentResult(
            signal     = VoteSignal.ABSTAIN,
            confidence = 0.0,
            reason     = reason,
            votes      = [],
        )
