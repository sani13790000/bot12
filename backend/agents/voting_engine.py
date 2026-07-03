"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine

Coordinates all agents, collects votes, applies weighted majority,
veto rules, tie-breaking, and circuit breaker integration.
FIX: Import AgentStatus, AgentResult, VoteResult from base_agent (not core modules).
MS-4: Sequential safe mode.
MS-5: Gather fallback with closed paren fix.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class VoteSignal(str, Enum):
    BUY     = "BUY"
    SELL    = "SELL"
    HOLD    = "HOLD"
    ABSTAIN = "ABSTAIN"


@dataclass
class VoteResult:
    agent_id:   str
    signal:     VoteSignal
    confidence: float
    weight:     float
    reason:     str     = ""
    error:      Optional[str] = None

    @property
    def weighted_score(self) -> float:
        return self.confidence * self.weight


@dataclass
class ConsensusResult:
    signal:        VoteSignal
    confidence:    float
    votes:         List[VoteResult]   = field(default_factory=list)
    buy_score:     float              = 0.0
    sell_score:    float              = 0.0
    hold_score:    float              = 0.0
    total_weight:  float              = 0.0
    veto_applied:  bool               = False
    veto_reason:   Optional[str]      = None
    latency_ms:    float              = 0.0
    ts:            float              = field(default_factory=time.time)


class VotingEngine:
    """
    Multi-agent voting engine.
    Collects signals from all registered agents and produces consensus.
    """

    _AGENT_TIMEOUT   = 5.0   # seconds per agent
    _MIN_CONFIDENCE  = 0.55  # minimum consensus confidence

    def __init__(self) -> None:
        self._agents:       List[Any]    = []
        self._config        = type('C', (), {
            'confidence_floor': self._MIN_CONFIDENCE,
            'sequential_mode':  False,
        })()
        self._log           = log
        self._circuit_open  = False

    # ── Agent registry ──────────────────────────────────────────────────────────────

    def register(self, agent: Any) -> None:
        self._agents.append(agent)
        self._log.info("VotingEngine: registered agent %s", getattr(agent, 'name', repr(agent)))

    # ── Public API ─────────────────────────────────────────────────────────────

    async def vote(self, context: Dict[str, Any]) -> ConsensusResult:
        """Collect votes from all agents and produce consensus."""
        t0 = time.perf_counter()

        if not self._agents:
            return ConsensusResult(signal=VoteSignal.HOLD, confidence=0.0)

        if self._config.sequential_mode:
            votes = await self._run_sequential_safe(self._agents, context)
        else:
            votes = await self._run_gather_safe(self._agents, context)

        consensus = self._compute_consensus(votes)
        consensus.latency_ms = (time.perf_counter() - t0) * 1000
        return consensus

    # ── Internal runners ──────────────────────────────────────────────────────────

    async def _run_gather_safe(
        self, agents: List[Any], context: Dict[str, Any]
    ) -> List[VoteResult]:
        """MS-5: asyncio.gather with per-agent timeout and fallback."""
        tasks = [
            asyncio.create_task(self._run_with_timeout(a, context))
            for a in agents
        ]
        raw = await asyncio.gather(*tasks, return_exceptions=True)

        results: List[VoteResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, Exception):
                name = getattr(agents[i], "name", f"Agent[{i}]")
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
        """MS-4 + MS-5: Sequential fallback mode."""
        results: List[VoteResult] = []
        for agent in agents:
            results.append(await self._run_with_timeout(agent, context))
        return results

    async def _run_with_timeout(
        self, agent: Any, context: Dict[str, Any]
    ) -> VoteResult:
        """Run a single agent with timeout."""
        name = getattr(agent, "name", repr(agent))
        try:
            result = await asyncio.wait_for(
                agent.analyze(context),
                timeout=self._AGENT_TIMEOUT,
            )
            if isinstance(result, VoteResult):
                return result
            # Adapt raw dict result
            return VoteResult(
                agent_id   = name,
                signal     = VoteSignal(result.get("signal", "HOLD")),
                confidence = float(result.get("confidence", 0.5)),
                weight     = getattr(agent, "weight", 1.0),
                reason     = result.get("reason", ""),
            )
        except asyncio.TimeoutError:
            self._log.warning("Agent %s timed out", name)
            return VoteResult(
                agent_id=name, signal=VoteSignal.ABSTAIN,
                confidence=0.0, weight=getattr(agent, "weight", 1.0),
                reason="timeout", error="TimeoutError",
            )
        except Exception as exc:
            self._log.error("Agent %s error: %s", name, exc)
            return VoteResult(
                agent_id=name, signal=VoteSignal.ABSTAIN,
                confidence=0.0, weight=getattr(agent, "weight", 1.0),
                reason=f"error: {exc}", error=str(exc),
            )

    def _compute_consensus(self, votes: List[VoteResult]) -> ConsensusResult:
        """Weighted majority voting."""
        buy_score = sell_score = hold_score = total_weight = 0.0

        for v in votes:
            if v.signal == VoteSignal.ABSTAIN:
                continue
            w = v.weight
            total_weight += w
            if v.signal == VoteSignal.BUY:
                buy_score  += v.confidence * w
            elif v.signal == VoteSignal.SELL:
                sell_score += v.confidence * w
            else:
                hold_score += v.confidence * w

        if total_weight == 0:
            return ConsensusResult(
                signal=VoteSignal.HOLD, confidence=0.0, votes=votes,
            )

        buy_n  = buy_score  / total_weight
        sell_n = sell_score / total_weight
        hold_n = hold_score / total_weight

        if buy_n >= sell_n and buy_n >= hold_n:
            signal, conf = VoteSignal.BUY,  buy_n
        elif sell_n >= buy_n and sell_n >= hold_n:
            signal, conf = VoteSignal.SELL, sell_n
        else:
            signal, conf = VoteSignal.HOLD, hold_n

        if conf < self._config.confidence_floor:
            signal, conf = VoteSignal.HOLD, conf

        return ConsensusResult(
            signal=signal, confidence=conf, votes=votes,
            buy_score=buy_n, sell_score=sell_n, hold_score=hold_n,
            total_weight=total_weight,
        )


voting_engine = VotingEngine()
