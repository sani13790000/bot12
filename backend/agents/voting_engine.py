"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine

Coordinates all agents, collects votes, applies weighted majority,
veto rules, tie-breaking, and circuit breaker integration.
FIX: Import AgentStatus, AgentResult, VoteResult from base_agent.
MS-4: Sequential fallback when gather fails.
MS-5: Per-agent error isolation (gather return_exceptions=True).
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


@dataclass
class VotingConfig:
    timeout_s:       float = 5.0
    quorum_pct:      float = 0.6
    confidence_floor: float = 0.3
    max_agents:      int   = 12


class VotingEngine:
    """Multi-agent weighted voting engine."""

    def __init__(self, config: Optional[VotingConfig] = None):
        self._config  = config or VotingConfig()
        self._agents:  List[BaseAgent] = []
        self._circuit_open: bool = False
        self._log = logging.getLogger(self.__class__.__name__)

    def register(self, agent: BaseAgent) -> None:
        """Register an agent."""
        if len(self._agents) >= self._config.max_agents:
            raise ValueError(f"Max {self._config.max_agents} agents allowed")
        self._agents.append(agent)
        self._log.info(f"Registered agent: {getattr(agent, 'agent_id', agent)}")

    def open_circuit(self) -> None:
        """Open circuit breaker — all votes return HOLD."""
        self._circuit_open = True
        self._log.warning("Circuit breaker OPEN")

    def close_circuit(self) -> None:
        """Close circuit breaker."""
        self._circuit_open = False
        self._log.info("Circuit breaker CLOSED")

    async def _run_with_timeout(
        self, agent: BaseAgent, context: Dict[str, Any]
    ) -> VoteResult:
        """Run single agent with timeout."""
        try:
            result = await asyncio.wait_for(
                agent.analyze(context), timeout=self._config.timeout_s
            )
            vote = result.vote
            return VoteResult(
                agent_id  = vote.agent_id,
                signal    = vote.signal,
                confidence= vote.confidence,
                weight    = vote.weight,
                reason    = vote.reason,
            )
        except asyncio.TimeoutError:
            name = getattr(agent, "agent_id", str(agent))
            self._log.warning(f"Agent {name} timed out")
            return VoteResult(
                agent_id  = name,
                signal    = VoteSignal.ABSTAIN,
                confidence= 0.0,
                weight    = getattr(agent, "weight", 1.0),
                reason    = "timeout",
            )
        except Exception as e:
            name = getattr(agent, "agent_id", str(agent))
            return VoteResult(
                agent_id  = name,
                signal    = VoteSignal.ABSTAIN,
                confidence= 0.0,
                weight    = getattr(agent, "weight", 1.0),
                reason    = f"error: {e}",
                error     = str(e),
            )

    async def run_parallel_safe(
        self, agents: List[Any], context: Dict[str, Any]
    ) -> List[VoteResult]:
        """MS-5: Parallel with per-agent error isolation."""
        tasks = [self._run_with_timeout(agent, context) for agent in agents]
        raw   = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[VoteResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = getattr(agents[i], "agent_id",
                               getattr(agents[i], "name", f"Agent[{i}]"))
                self._log.error("MS-5 gather fallback for %s: %s", name, item)
                results.append(
                    VoteResult(
                        agent_id  = name,
                        signal    = VoteSignal.ABSTAIN,
                        confidence= 0.0,
                        weight    = getattr(agents[i], "weight", 1.0),
                        reason    = f"error: {item}",
                        error     = str(item),
                    )
                )
            else:
                results.append(item)
        return results

    async def _run_sequential_safe(
        self, agents: List[Any], context: Dict[str, Any]
    ) -> List[VoteResult]:
        """MS-4 + MS-5: Sequential fallback mode."""
        results: List[VoteResult] = []
        for agent in agents:
            results.append(await self._run_with_timeout(agent, context))
        return results

    def _tally(
        self, votes: List[VoteResult]
    ) -> Optional["FinalDecision"]:
        """Tally weighted votes and produce final decision."""
        if not votes:
            return None

        weight_map: Dict[VoteSignal, float] = {s: 0.0 for s in VoteSignal}
        total_weight = 0.0
        participating = 0

        for v in votes:
            if v.signal == VoteSignal.ABSTAIN:
                continue
            weight_map[v.signal] += v.weight * v.confidence
            total_weight         += v.weight
            participating        += 1

        if participating == 0 or total_weight == 0:
            return None

        quorum = participating / max(len(votes), 1)
        if quorum < self._config.quorum_pct:
            return None

        best_signal    = max(weight_map, key=lambda s: weight_map[s])
        best_confidence = weight_map[best_signal] / total_weight

        if best_confidence < self._config.confidence_floor:
            return None

        return FinalDecision(
            signal      = best_signal,
            confidence  = best_confidence,
            votes       = votes,
            quorum_reached = True,
        )

    async def vote(self, context: Dict[str, Any]) -> Optional["FinalDecision"]:
        """Run voting cycle and return final decision."""
        if self._circuit_open:
            self._log.warning("Circuit open — returning HOLD")
            return FinalDecision(
                signal      = VoteSignal.HOLD,
                confidence  = 0.0,
                votes       = [],
                quorum_reached = False,
            )

        agents = list(self._agents)
        if not agents:
            return None

        try:
            results = await self.run_parallel_safe(agents, context)
        except Exception as e:
            self._log.error("Parallel gather failed, falling back: %s", e)
            results = await self._run_sequential_safe(agents, context)

        return self._tally(results)

    def status(self) -> Dict[str, Any]:
        return {
            "agents":       len(self._agents),
            "circuit_open": self._circuit_open,
            "config": {
                "timeout_s":        self._config.timeout_s,
                "quorum_pct":       self._config.quorum_pct,
                "confidence_floor": self._config.confidence_floor,
            },
        }


@dataclass
class FinalDecision:
    signal:        VoteSignal
    confidence:    float
    votes:         List[VoteResult]
    quorum_reached: bool


voting_engine = VotingEngine()
