"""
backend/agents/voting_engine.py
Galaxy Vast AI - Enterprise Voting Engine

Coordinates all agents, collects votes, applies weighted majority.
"""
from __future__ import annotations
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from .base_agent import AgentResult, AgentStatus, AgentVote, BaseAgent, VoteResult, VoteSignal

_LOG = logging.getLogger(__name__)
_RISK_AGENT_NAME = "risk_agent"
_DEFAULT_TIMEOUT = 10.0


@dataclass
class VotingConfig:
    timeout_s: float = _DEFAULT_TIMEOUT
    min_agents: int = 3
    quorum_pct: float = 0.6
    confidence_floor: float = 55.0
    sequential_fallback: bool = True


@dataclass
class FinalVote:
    """Aggregated vote result from all agents."""
    signal: VoteSignal
    confidence: float
    reason: str
    votes: List[VoteResult] = field(default_factory=list)
    blocked: bool = False
    block_reason: str = ""

    @property
    def approved(self) -> bool:
        return not self.blocked and self.signal in (VoteSignal.BUY, VoteSignal.SELL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal": self.signal.value,
            "confidence": round(self.confidence, 4),
            "reason": self.reason,
            "approved": self.approved,
            "blocked": self.blocked,
            "block_reason": self.block_reason,
            "vote_count": len(self.votes),
        }


class VotingEngine:
    """Weighted majority voting with veto, quorum, and circuit breaker."""

    def __init__(
        self,
        agents: Optional[List[Any]] = None,
        config: Optional[VotingConfig] = None,
    ) -> None:
        self._agents: List[Any] = agents or []
        self._config = config or VotingConfig()
        self._circuit_open = False
        self._log = logging.getLogger(f"{__name__}.engine")

    def register_agent(self, agent: Any) -> None:
        self._agents.append(agent)

    async def vote(self, context: Dict[str, Any]) -> FinalVote:
        """Run all agents and aggregate their votes."""
        if not self._agents:
            return FinalVote(
                signal=VoteSignal.NEUTRAL,
                confidence=0.0,
                reason="no_agents",
                blocked=True,
                block_reason="no_agents",
            )
        veto = await self._check_risk_veto(context)
        if veto is not None:
            return veto
        non_risk = [
            a for a in self._agents
            if getattr(a, "agent_id", getattr(a, "name", "")) != _RISK_AGENT_NAME
        ]
        if not non_risk:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=0.0, reason="no_non_risk_agents")
        try:
            votes = await self._run_parallel_safe(non_risk, context)
        except Exception as exc:
            self._log.warning("Parallel vote failed, sequential fallback: %s", exc)
            if self._config.sequential_fallback:
                votes = await self._run_sequential_safe(non_risk, context)
            else:
                raise
        return self._aggregate(votes)

    async def _check_risk_veto(self, context: Dict[str, Any]) -> Optional[FinalVote]:
        """Run the risk agent; return a BLOCKED FinalVote if it vetoes."""
        risk_agent = next(
            (a for a in self._agents if getattr(a, "agent_id", getattr(a, "name", "")) == _RISK_AGENT_NAME),
            None,
        )
        if risk_agent is None:
            return None
        try:
            result = await asyncio.wait_for(risk_agent.analyze(context), timeout=self._config.timeout_s)
            if getattr(result, "signal", None) == VoteSignal.ABSTAIN:
                reason = getattr(result, "reason", "risk_veto")
                self._log.warning("Risk veto triggered reason=%s", reason)
                return FinalVote(
                    signal=VoteSignal.NEUTRAL,
                    confidence=100.0,
                    reason=f"risk_veto: {reason}",
                    blocked=True,
                    block_reason=reason,
                )
        except asyncio.TimeoutError:
            self._log.warning("risk_agent timeout")
        except Exception as exc:
            self._log.error("risk_agent failed: %s", exc)
        return None

    async def _run_parallel_safe(self, agents: List[Any], context: Dict[str, Any]) -> List[VoteResult]:
        """Parallel with per-agent error isolation."""
        tasks = [self._run_with_timeout(agent, context) for agent in agents]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[VoteResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = getattr(agents[i], "agent_id", getattr(agents[i], "name", f"Agent[{i}]"))
                self._log.error("Gather fallback for %s: %s", name, item)
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

    async def _run_sequential_safe(self, agents: List[Any], context: Dict[str, Any]) -> List[VoteResult]:
        """Sequential fallback mode."""
        results: List[VoteResult] = []
        for agent in agents:
            results.append(await self._run_with_timeout(agent, context))
        return results

    async def _run_with_timeout(self, agent: Any, context: Dict[str, Any]) -> VoteResult:
        """Run a single agent with timeout. Never raises."""
        agent_id = getattr(agent, "agent_id", getattr(agent, "name", "unknown"))
        weight = getattr(agent, "weight", 1.0)
        try:
            result = await asyncio.wait_for(agent.analyze(context), timeout=self._config.timeout_s)
            return result
        except asyncio.TimeoutError:
            self._log.warning("agent_timeout agent=%s", agent_id)
            return VoteResult(agent_id=agent_id, signal=VoteSignal.ABSTAIN, confidence=0.0, weight=weight, reason="timeout", error="timeout")
        except Exception as exc:
            self._log.error("agent_error agent=%s: %s", agent_id, exc)
            return VoteResult(agent_id=agent_id, signal=VoteSignal.ABSTAIN, confidence=0.0, weight=weight, reason=f"error: {exc}", error=str(exc))

    def _aggregate(self, votes: List[VoteResult]) -> FinalVote:
        """Weighted majority aggregation with quorum check."""
        active = [v for v in votes if v.signal != VoteSignal.ABSTAIN]
        if not active:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=0.0, reason="all_agents_abstained", votes=votes)
        if len(active) < self._config.min_agents:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=0.0, reason=f"quorum_not_met({len(active)}<{self._config.min_agents})", votes=votes)
        buy_weight = sell_weight = total_weight = confidence_sum = 0.0
        reasons: List[str] = []
        for v in active:
            w = v.weight
            conf = v.confidence
            if not (isinstance(conf, float) and conf == conf and abs(conf) != float("inf")):
                conf = 0.0
            total_weight += w
            confidence_sum += conf * w
            if v.signal == VoteSignal.BUY:
                buy_weight += w
            elif v.signal == VoteSignal.SELL:
                sell_weight += w
            if v.reason:
                reasons.append(f"{v.agent_id}: {v.reason}")
        if total_weight == 0:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=0.0, reason="zero_weight", votes=votes)
        avg_conf = confidence_sum / total_weight
        if avg_conf < self._config.confidence_floor:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=avg_conf, reason=f"confidence_below_floor({avg_conf:.1f}<{self._config.confidence_floor})", votes=votes)
        buy_pct = buy_weight / total_weight
        sell_pct = sell_weight / total_weight
        reason = "; ".join(reasons)
        if buy_pct >= self._config.quorum_pct:
            return FinalVote(signal=VoteSignal.BUY, confidence=avg_conf, reason=reason, votes=votes)
        if sell_pct >= self._config.quorum_pct:
            return FinalVote(signal=VoteSignal.SELL, confidence=avg_conf, reason=reason, votes=votes)
        return FinalVote(signal=VoteSignal.NEUTRAL, confidence=avg_conf, reason=f"no_quorum(buy={buy_pct:.0%} sell={sell_pct:.0%})", votes=votes)

    async def health(self) -> Dict[str, Any]:
        return {"status": "ok", "agents": len(self._agents), "circuit_open": self._circuit_open}
