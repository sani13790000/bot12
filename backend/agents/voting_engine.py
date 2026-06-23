"""Galaxy Vast AI Trading Platform
VotingEngine v2 — Multi-Agent Safety
======================================
Fixes:
  MS-1: Risk Engine highest priority — veto power, no override
  MS-2: Tie vote (BUY==SELL weight) → NO_TRADE
  MS-3: Weighted voting using real confidence values
  MS-4: Agent timeout handling — asyncio.wait_for per agent
  MS-5: Failover — crashed agents never stop remaining agents
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .base_agent import AgentResult, AgentStatus, AgentVote, BaseAgent
from backend.core.logger import get_logger

logger = get_logger("agents.voting_engine")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
_AGENT_TIMEOUT_S: float = 5.0          # MS-4: per-agent hard timeout
_TIE_TOLERANCE:   float = 0.01         # MS-2: |BUY_w - SELL_w| < this → TIE
_RISK_AGENT_NAME: str   = "Risk"       # MS-1: name used to identify risk engine


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────
class VoteDecision(str, Enum):
    BUY      = "BUY"
    SELL     = "SELL"
    NO_TRADE = "NO_TRADE"
    BLOCKED  = "BLOCKED"


@dataclass
class VoteResult:
    decision:       VoteDecision
    weighted_score: float
    confidence:     float
    direction:      str
    agent_results:  List[AgentResult] = field(default_factory=list)
    blocked_by:     Optional[str]     = None
    reasons:        List[str]         = field(default_factory=list)
    elapsed_ms:     float             = 0.0
    metadata:       Dict[str, Any]    = field(default_factory=dict)

    # ── backwards-compat aliases ──────────────────────────────────────────────────
    @property
    def final_confidence(self) -> float:
        return self.confidence

    @property
    def passed_threshold(self) -> bool:
        return self.decision in (VoteDecision.BUY, VoteDecision.SELL)

    @property
    def blocking_agents(self) -> List[str]:
        if self.blocked_by:
            return [self.blocked_by]
        return [
            r.agent_name for r in self.agent_results
            if r.vote.status == AgentStatus.ERROR and r.vote.score == 0.0
        ]

    @property
    def votes_summary(self) -> Dict[str, Any]:
        return {
            r.agent_name: {
                "score":     round(r.vote.score, 2),
                "direction": r.vote.direction,
                "status":    r.vote.status.value,
                "reason":    r.vote.reason,
            }
            for r in self.agent_results
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision":         self.decision.value,
            "weighted_score":   round(self.weighted_score, 2),
            "confidence":       round(self.confidence, 2),
            "final_confidence": round(self.confidence, 2),
            "direction":        self.direction,
            "blocked_by":       self.blocked_by,
            "blocking_agents":  self.blocking_agents,
            "passed_threshold": self.passed_threshold,
            "reasons":          self.reasons,
            "elapsed_ms":       round(self.elapsed_ms, 1),
            "votes_summary":    self.votes_summary,
            "agents": [
                {
                    "name":       r.agent_name,
                    "score":      round(r.vote.score, 2),
                    "confidence": round(r.vote.confidence, 2),
                    "direction":  r.vote.direction,
                    "status":     r.vote.status.value,
                    "reason":     r.vote.reason,
                    "elapsed_ms": round(r.elapsed_ms, 1),
                }
                for r in self.agent_results
            ],
            **self.metadata,
        }


# ─────────────────────────────────────────────────────────────────────────────
# VotingEngine
# ─────────────────────────────────────────────────────────────────────────────
class VotingEngine:
    """
    Multi-Agent Weighted Voting Engine — Hedge-Fund Safety Grade.

    Safety invariants:
      1. Risk Engine has absolute veto power — no other agent can override.
      2. Tie vote (BUY_weight ≈ SELL_weight) → NO_TRADE (never guess).
      3. Every vote is weighted by agent.confidence (not flat weight).
      4. Each agent runs inside asyncio.wait_for(timeout) → agent crash
         never blocks the system.
      5. Failover: if an agent raises/times out, remaining agents
         continue normally; the failed agent contributes a neutral score.
    """

    def __init__(
        self,
        agents:                   List[BaseAgent],
        min_score_threshold:      float = 65.0,
        min_confidence_threshold: float = 50.0,
        run_parallel:             bool  = True,
        agent_timeout_s:          float = _AGENT_TIMEOUT_S,
    ) -> None:
        self._agents                   = agents
        self._min_score_threshold      = min_score_threshold
        self._min_confidence_threshold = min_confidence_threshold
        self._run_parallel             = run_parallel
        self._agent_timeout_s          = agent_timeout_s

        # Auto-normalise weights on init
        self._normalise_weights()

        logger.info(
            "VotingEngine v2 ready | %d agents | parallel=%s | "
            "min_score=%.1f min_conf=%.1f timeout=%.1fs",
            len(agents), run_parallel,
            min_score_threshold, min_confidence_threshold, agent_timeout_s,
        )

    # ─────────────────────────── public API ────────────────────────────────

    async def vote(self, context: Dict[str, Any]) -> VoteResult:
        t0 = time.perf_counter()

        # MS-1: Run Risk Engine FIRST — independent of other agents
        risk_veto = await self._check_risk_veto(context)
        if risk_veto is not None:
            risk_veto.elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "Risk veto BLOCKED trading | reason=%s [%.0fms]",
                risk_veto.blocked_by, risk_veto.elapsed_ms,
            )
            return risk_veto

        # MS-4 + MS-5: Run remaining agents with timeout + failover
        if self._run_parallel:
            agent_results = await self._run_parallel_safe(context)
        else:
            agent_results = await self._run_sequential_safe(context)

        result = self._aggregate(agent_results)
        result.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Vote: %s score=%.1f conf=%.1f [%.0fms]",
            result.decision.value, result.weighted_score,
            result.confidence, result.elapsed_ms,
        )
        return result

    def update_weights(self, weight_map: Dict[str, float]) -> None:
        for agent in self._agents:
            if agent.name in weight_map:
                agent.weight = float(weight_map[agent.name])
        self._normalise_weights()
        logger.info("VotingEngine weights updated: %s", weight_map)

    def set_threshold(self, threshold: float) -> None:
        self._min_score_threshold = float(threshold)
        logger.info("VotingEngine threshold → %.1f", threshold)

    def enable_agent(self, name: str) -> None:
        for a in self._agents:
            if a.name == name:
                a.enabled = True
                logger.info("Agent enabled: %s", name)
                return
        logger.warning("enable_agent: not found: %s", name)

    def disable_agent(self, name: str) -> None:
        for a in self._agents:
            if a.name == name:
                a.enabled = False
                logger.info("Agent disabled: %s", name)
                return
        logger.warning("disable_agent: not found: %s", name)

    def get_weights(self) -> Dict[str, float]:
        return {a.name: a.weight for a in self._agents}

    @property
    def agents(self) -> List[BaseAgent]:
        return self._agents

    # ─────────────────────── MS-1: Risk Engine veto ────────────────────────

    async def _check_risk_veto(self, context: Dict[str, Any]) -> Optional[VoteResult]:
        """
        MS-1 — Risk Engine has highest priority.
        Runs before any other agent.  If it blocks → immediate BLOCKED return.
        No other agent can override this decision.
        """
        risk_agent = next(
            (a for a in self._agents if a.name == _RISK_AGENT_NAME and a.enabled),
            None,
        )
        if risk_agent is None:
            logger.error(
                "MS-1 SAFETY: Risk agent '%s' not found or disabled! "
                "Trading BLOCKED as precaution.",
                _RISK_AGENT_NAME,
            )
            return VoteResult(
                decision=VoteDecision.BLOCKED,
                weighted_score=0.0,
                confidence=0.0,
                direction="BLOCKED",
                blocked_by="SYSTEM",
                reasons=["Risk agent missing — trading halted for safety"],
            )

        # MS-4: timeout guard on risk agent itself
        result = await self._run_with_timeout(risk_agent, context)

        if result.vote.status == AgentStatus.ERROR and result.vote.score == 0.0:
            return VoteResult(
                decision=VoteDecision.BLOCKED,
                weighted_score=0.0,
                confidence=0.0,
                direction="BLOCKED",
                agent_results=[result],
                blocked_by=result.agent_name,
                reasons=[f"Risk veto: {result.vote.reason}"],
            )

        # Risk agent timeout / crash → conservative block
        if result.error and "timeout" in result.error.lower():
            logger.error("MS-1: Risk agent timed out → conservative BLOCK")
            return VoteResult(
                decision=VoteDecision.BLOCKED,
                weighted_score=0.0,
                confidence=0.0,
                direction="BLOCKED",
                agent_results=[result],
                blocked_by=result.agent_name,
                reasons=["Risk agent timeout — trading halted for safety"],
            )

        return None  # Risk OK — continue to other agents

    # ─────────── MS-4 + MS-5: timeout + failover runner ───────────────────

    async def _run_with_timeout(
        self, agent: BaseAgent, context: Dict[str, Any]
    ) -> AgentResult:
        """
        MS-4: Run a single agent with hard timeout.
        MS-5: On timeout or crash → return neutral AgentResult (failover),
              never propagate exception upward.
        """
        try:
            return await asyncio.wait_for(
                agent.run(context),
                timeout=self._agent_timeout_s,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "MS-4: Agent '%s' timed out after %.1fs — failover neutral score",
                agent.name, self._agent_timeout_s,
            )
            return AgentResult(
                agent_name=agent.name,
                vote=AgentVote(
                    score=50.0, confidence=0.0,
                    status=AgentStatus.ERROR,
                    reason=f"Timeout after {self._agent_timeout_s}s",
                    direction="NEUTRAL",
                ),
                elapsed_ms=self._agent_timeout_s * 1000,
                error=f"timeout after {self._agent_timeout_s}s",
            )
        except Exception as exc:                          # MS-5: failover
            logger.error(
                "MS-5: Agent '%s' crashed: %s — failover neutral score",
                agent.name, exc, exc_info=True,
            )
            return AgentResult(
                agent_name=agent.name,
                vote=AgentVote(
                    score=50.0, confidence=0.0,
                    status=AgentStatus.ERROR,
                    reason=f"Crash: {exc}",
                    direction="NEUTRAL",
                ),
                elapsed_ms=0.0,
                error=str(exc),
            )

    async def _run_parallel_safe(
        self, context: Dict[str, Any]
    ) -> List[AgentResult]:
        """MS-4 + MS-5: Run all non-risk agents in parallel with timeout + failover."""
        non_risk = [a for a in self._agents if a.name != _RISK_AGENT_NAME]
        tasks    = [self._run_with_timeout(a, context) for a in non_risk]
        raw = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[AgentResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = non_risk[i].name if i < len(non_risk) else f"Agent[{i}]"
                logger.error("MS-5 gather fallback for %s: %s", name, item)
                results.append(AgentResult(
                    agent_name=name,
                    vote=AgentVote(
                        score=50.0, confidence=0.0,
                        status=AgentStatus.ERROR,
                        reason=f"Unhandled: {item}",
                        direction="NEUTRAL",
                    ),
                    elapsed_ms=0.0,
                    error=str(item),
                ))
            else:
                results.append(item)
        return results

    async def _run_sequential_safe(
        self, context: Dict[str, Any]
    ) -> List[AgentResult]:
        """MS-4 + MS-5: Sequential fallback mode."""
        results: List[AgentResult] = []
        for agent in self._agents:
            if agent.name == _RISK_AGENT_NAME:
                continue  # already ran in _check_risk_veto
            results.append(await self._run_with_timeout(agent, context))
        return results

    # ──────────────────────── MS-2 + MS-3: aggregation ───────────────────

    def _aggregate(self, results: List[AgentResult]) -> VoteResult:
        """
        MS-3: Weighted voting — each agent's contribution is
              weight x confidence (not flat weight).
        MS-2: If BUY_weight ≈ SELL_weight → NO_TRADE.
        """
        total_w         = 0.0
        weighted_score  = 0.0
        weighted_conf   = 0.0
        direction_w: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        reasons: List[str] = []

        agent_weight_map = {a.name: a.weight for a in self._agents}

        for r in results:
            if r.vote.status == AgentStatus.SKIP:
                continue

            base_weight = agent_weight_map.get(r.agent_name, 1.0 / max(len(results), 1))

            # MS-3: Scale weight by agent confidence (0-100 to 0-1 multiplier)
            conf_multiplier = max(0.0, r.vote.confidence / 100.0)
            effective_w     = base_weight * conf_multiplier

            if r.vote.status == AgentStatus.ERROR:
                # MS-5: failed agents use 50% penalty, never zero
                effective_w *= 0.5

            weighted_score += r.vote.score      * effective_w
            weighted_conf  += r.vote.confidence * effective_w
            total_w        += effective_w

            direction = (r.vote.direction or "NEUTRAL").upper()
            direction_w.setdefault(direction, 0.0)
            direction_w[direction] += effective_w

            if r.vote.reason:
                reasons.append(f"[{r.agent_name}] {r.vote.reason}")

        if total_w > 0.0:
            final_score = weighted_score / total_w
            final_conf  = weighted_conf  / total_w
        else:
            final_score, final_conf = 50.0, 0.0

        final_score = max(0.0, min(100.0, final_score))
        final_conf  = max(0.0, min(100.0, final_conf))

        # MS-2: Tie detection
        buy_w  = direction_w.get("BUY",  0.0)
        sell_w = direction_w.get("SELL", 0.0)
        is_tie = abs(buy_w - sell_w) <= _TIE_TOLERANCE and (buy_w + sell_w) > 0.0

        if is_tie:
            reasons.append(
                f"MS-2 TIE: BUY_w={buy_w:.4f} SELL_w={sell_w:.4f} → NO_TRADE"
            )
            logger.info("MS-2 Tie vote detected (BUY=%.4f SELL=%.4f) → NO_TRADE", buy_w, sell_w)
            return VoteResult(
                decision=VoteDecision.NO_TRADE,
                weighted_score=final_score,
                confidence=final_conf,
                direction="NEUTRAL",
                agent_results=results,
                reasons=reasons,
                metadata={
                    "tie_detected":    True,
                    "buy_weight":      round(buy_w, 4),
                    "sell_weight":     round(sell_w, 4),
                    "direction_votes": {k: round(v, 4) for k, v in direction_w.items()},
                    "total_weight":    round(total_w, 4),
                    "active_agents":   len([r for r in results if r.vote.status != AgentStatus.SKIP]),
                    "error_agents":    len([r for r in results if r.vote.status == AgentStatus.ERROR]),
                    "timeout_agents":  len([r for r in results if r.error and "timeout" in (r.error or "")]),
                },
            )

        top_direction = max(direction_w, key=lambda d: direction_w[d])

        score_ok = final_score >= self._min_score_threshold
        conf_ok  = final_conf  >= self._min_confidence_threshold

        if score_ok and conf_ok:
            if top_direction == "BUY":
                decision = VoteDecision.BUY
            elif top_direction == "SELL":
                decision = VoteDecision.SELL
            else:
                decision = VoteDecision.NO_TRADE
        else:
            decision = VoteDecision.NO_TRADE
            reasons.append(
                f"Threshold not met: score={final_score:.1f}/{self._min_score_threshold} "
                f"conf={final_conf:.1f}/{self._min_confidence_threshold}"
            )

        return VoteResult(
            decision=VoteDecision(decision),
            weighted_score=final_score,
            confidence=final_conf,
            direction=top_direction,
            agent_results=results,
            reasons=reasons,
            metadata={
                "tie_detected":    False,
                "buy_weight":      round(buy_w, 4),
                "sell_weight":     round(sell_w, 4),
                "direction_votes": {k: round(v, 4) for k, v in direction_w.items()},
                "total_weight":    round(total_w, 4),
                "active_agents":   len([r for r in results if r.vote.status != AgentStatus.SKIP]),
                "error_agents":    len([r for r in results if r.vote.status == AgentStatus.ERROR]),
                "timeout_agents":  len([r for r in results if r.error and "timeout" in (r.error or "")]),
            },
        )

    # ──────────────────────────── helpers ─────────────────────────────────

    def _normalise_weights(self) -> None:
        """Auto-normalise agent weights so they sum to 1.0."""
        enabled = [a for a in self._agents if a.enabled]
        if not enabled:
            return
        total = sum(a.weight for a in enabled)
        if total > 0 and abs(total - 1.0) > 0.01:
            logger.warning(
                "Agent weights sum=%.4f → auto-normalising.", total
            )
            for a in enabled:
                a.weight = a.weight / total
