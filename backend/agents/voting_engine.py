"""
backend/agents/voting_engine.py
Galaxy Vast AI — Enterprise Voting Engine

وظیفه: هماهنگی تمام agent‌ها، جمع‌آوری رأی‌ها، اعمال اکثریت وزنی،
       قوانین veto، tie-breaking، و circuit-breaker integration.

اصلاحات اعمال‌شده:
  FIX-1: def __init_( → def __init__(   (underscore اضافه)
  FIX-2: NUUTRAL → NEUTRAL              (typo)
  FIX-3: _RSIK_AGENT_NAME → _RISK_AGENT_NAME  (typo)
  FIX-4: resut.reason → result.reason   (typo)
  FIX-5: annotaton → annotations        (typo)
  FIX-6: run_parallel_safe → _run_parallel_safe  (underscore private)
  FIX-7: run_with_timeout → _run_with_timeout    (underscore private)
  FIX-8: Self._config → self._config    (حرف بزرگ)
  MS-4:  Sequential fallback when gather fails.
  MS-5:  Per-agent error isolation (gather return_exceptions=True).
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


_LOG               = logging.getLogger(__name__)
_RISK_AGENT_NAME   = "risk_agent"          # FIX-3: بود _RSIK_AGENT_NAME
_DEFAULT_TIMEOUT   = 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VotingConfig:
    """پارامترهای قابل تنظیم موتور رأی‌گیری."""

    timeout_s:           float = _DEFAULT_TIMEOUT
    min_agents:          int   = 3
    quorum_pct:          float = 0.6     # ۶۰٪ اکثریت وزنی
    confidence_floor:    float = 55.0    # حداقل اطمینان aggregate
    sequential_fallback: bool  = True    # MS-4


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class FinalVote:
    """نتیجه aggregate شده رأی‌گیری از همه agent‌ها."""

    signal:       VoteSignal
    confidence:   float
    reason:       str
    votes:        List[VoteResult] = field(default_factory=list)
    blocked:      bool = False
    block_reason: str  = ""

    @property
    def approved(self) -> bool:
        """آیا سیگنال معتبر و تأیید شده است؟"""
        return not self.blocked and self.signal in (VoteSignal.BUY, VoteSignal.SELL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signal":       self.signal.value,
            "confidence":   round(self.confidence, 4),
            "reason":       self.reason,
            "approved":     self.approved,
            "blocked":      self.blocked,
            "block_reason": self.block_reason,
            "vote_count":   len(self.votes),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main engine
# ─────────────────────────────────────────────────────────────────────────────

class VotingEngine:
    """
    Weighted majority voting با veto، quorum، و circuit breaker.

    جریان اجرا:
      1. risk_agent veto gate (اگر ABSTAIN برگرداند → بلوک)
      2. جمع‌آوری موازی رأی‌های non-risk agent‌ها
      3. Aggregate وزنی
    """

    def __init__(
        self,
        agents: Optional[List[Any]] = None,
        config: Optional[VotingConfig] = None,
    ) -> None:
        self._agents:       List[Any]    = agents or []
        self._config:       VotingConfig = config or VotingConfig()
        self._circuit_open: bool         = False
        self._log = logging.getLogger(f"{__name__}.engine")

    def register_agent(self, agent: Any) -> None:
        self._agents.append(agent)

    async def vote(self, context: Dict[str, Any]) -> FinalVote:
        """همه agent‌ها را اجرا کن و رأی‌هایشان را aggregate کن."""
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
            self._log.warning("Parallel_vote failed, sequential fallback: %s", exc)
            if self._config.sequential_fallback:
                votes = await self._run_sequential_safe(non_risk, context)
            else:
                raise
        return self._aggregate(votes)

    async def health(self) -> Dict[str, Any]:
        return {
            "status":        "ok",
            "agents":        len(self._agents),
            "circuit_open":  self._circuit_open,
            "config": {
                "timeout_s":        self._config.timeout_s,
                "quorum_pct":       self._config.quorum_pct,
                "confidence_floor": self._config.confidence_floor,
            },
        }

    async def _check_risk_veto(self, context: Dict[str, Any]) -> Optional[FinalVote]:
        risk_agent = next(
            (a for a in self._agents
             if getattr(a, "agent_id", getattr(a, "name", "")) == _RISK_AGENT_NAME),
            None,
        )
        if risk_agent is None:
            return None
        try:
            result = await asyncio.wait_for(
                risk_agent.analyze(context), timeout=self._config.timeout_s
            )
            if getattr(result, "signal", None) == VoteSignal.ABSTAIN:
                reason = getattr(result, "reason", "risk_veto")  # FIX-4: بود resut
                self._log.warning("Risk veto triggered reason=%s", reason)
                return FinalVote(
                    signal=VoteSignal.NEUTRAL, confidence=100.0,
                    reason=f"risk_veto: {reason}", blocked=True, block_reason=reason,
                )
        except asyncio.TimeoutError:
            self._log.warning("risk_agent timeout")
        except Exception as exc:
            self._log.error("risk_agent failed: %s", exc)
        return None

    async def _run_parallel_safe(self, agents: List[Any], context: Dict[str, Any]) -> List[VoteResult]:
        tasks = [self._run_with_timeout(agent, context) for agent in agents]
        raw   = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[VoteResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = getattr(agents[i], "agent_id", getattr(agents[i], "name", f"Agent[{i}]"))
                self._log.error("MS-5 gather fallback for %s: %s", name, item)
                results.append(VoteResult(
                    agent_id=name, signal=VoteSignal.ABSTAIN, confidence=0.0,
                    weight=getattr(agents[i], "weight", 1.0),
                    reason=f"error: {item}", error=str(item),
                ))
            else:
                results.append(item)
        return results

    async def _run_sequential_safe(self, agents: List[Any], context: Dict[str, Any]) -> List[VoteResult]:
        results: List[VoteResult] = []
        for agent in agents:
            results.append(await self._run_with_timeout(agent, context))
        return results

    async def _run_with_timeout(self, agent: Any, context: Dict[str, Any]) -> VoteResult:
        agent_id = getattr(agent, "agent_id", getattr(agent, "name", "unknown"))
        weight   = getattr(agent, "weight", 1.0)
        try:
            return await asyncio.wait_for(agent.analyze(context), timeout=self._config.timeout_s)
        except asyncio.TimeoutError:
            self._log.warning("agent_timeout agent=%s", agent_id)
            return VoteResult(agent_id=agent_id, signal=VoteSignal.ABSTAIN,
                              confidence=0.0, weight=weight, reason="timeout", error="timeout")
        except Exception as exc:
            self._log.error("agent_error agent=%s: %s", agent_id, exc)
            return VoteResult(agent_id=agent_id, signal=VoteSignal.ABSTAIN,
                              confidence=0.0, weight=weight,
                              reason=f"error: {exc}", error=str(exc))

    def _aggregate(self, votes: List[VoteResult]) -> FinalVote:
        active = [v for v in votes if v.signal != VoteSignal.ABSTAIN]
        if not active:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=0.0,
                             reason="all_agents_abstained", votes=votes)
        if len(active) < self._config.min_agents:
            return FinalVote(
                signal=VoteSignal.NEUTRAL, confidence=0.0,
                reason=f"quorum_not_met({len(active)}<{self._config.min_agents})",
                votes=votes,
            )
        buy_weight = sell_weight = total_weight = confidence_sum = 0.0
        reasons: List[str] = []
        for v in active:
            w    = v.weight
            conf = v.confidence
            if not (isinstance(conf, float) and conf == conf and abs(conf) != float("inf")):
                conf = 0.0
            total_weight   += w
            confidence_sum += conf * w
            if v.signal == VoteSignal.BUY:
                buy_weight  += w
            elif v.signal == VoteSignal.SELL:
                sell_weight += w
            if v.reason:
                reasons.append(f"{v.agent_id}: {v.reason}")
        if total_weight == 0:
            return FinalVote(signal=VoteSignal.NEUTRAL, confidence=0.0,
                             reason="zero_weight", votes=votes)
        avg_conf = confidence_sum / total_weight
        if avg_conf < self._config.confidence_floor:
            return FinalVote(
                signal=VoteSignal.NEUTRAL, confidence=avg_conf,
                reason=f"confidence_below_floor({avg_conf:.1f}<{self._config.confidence_floor})",
                votes=votes,
            )
        buy_pct  = buy_weight  / total_weight
        sell_pct = sell_weight / total_weight
        reason   = "; ".join(reasons)
        if buy_pct >= self._config.quorum_pct:
            return FinalVote(signal=VoteSignal.BUY, confidence=avg_conf,
                             reason=reason, votes=votes)
        if sell_pct >= self._config.quorum_pct:
            return FinalVote(signal=VoteSignal.SELL, confidence=avg_conf,
                             reason=reason, votes=votes)
        return FinalVote(
            signal=VoteSignal.NEUTRAL, confidence=avg_conf,
            reason=f"No_quorum(buy={buy_pct:.0%} sell={sell_pct:.0%})",
            votes=votes,
        )


voting_engine = VotingEngine()
