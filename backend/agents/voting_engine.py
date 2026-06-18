"""
Galaxy Vast AI Trading Platform
════════════════════════════════
Voting Engine — موتور رأی‌گیری وزن‌دار Multi-Agent
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from backend.core.logger import get_logger

from .base_agent import AgentResult, AgentStatus, AgentVote, BaseAgent


class TradeDecision(str, Enum):
    BUY      = "BUY"
    SELL     = "SELL"
    NO_TRADE = "NO_TRADE"
    BLOCKED  = "BLOCKED"


@dataclass
class VoteResult:
    """نتیجه نهایی رأی‌گیری تمام Agentها."""
    decision:          TradeDecision
    final_score:       float
    final_confidence:  float
    weighted_score:    float
    agent_results:     List[AgentResult]
    votes_summary:     Dict[str, Dict]
    blocking_agents:   List[str]
    direction:         Optional[str]
    passed_threshold:  bool
    threshold_used:    float
    total_weight:      float
    reason:            str
    metadata:          Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision":         self.decision.value,
            "final_score":      round(self.final_score, 2),
            "final_confidence": round(self.final_confidence, 2),
            "weighted_score":   round(self.weighted_score, 2),
            "direction":        self.direction,
            "passed_threshold": self.passed_threshold,
            "threshold_used":   self.threshold_used,
            "blocking_agents":  self.blocking_agents,
            "reason":           self.reason,
            "votes": {
                name: {
                    "score":      round(v["score"], 2),
                    "confidence": round(v["confidence"], 2),
                    "weight":     round(v["weight"], 3),
                    "status":     v["status"],
                    "reason":     v["reason"],
                }
                for name, v in self.votes_summary.items()
            },
        }


class VotingEngine:
    """
    موتور رأی‌گیری وزن‌دار:

    فرمول:
        weighted_score = Σ(agent.score × agent.weight × agent.confidence/100)
                       / Σ(agent.weight × agent.confidence/100)

    قوانین:
    1. اگر هر Agent با status=ERROR و score=0 باشد → BLOCKED
    2. اگر weighted_score < threshold → NO_TRADE
    3. اگر weighted_score >= threshold → BUY یا SELL
    """

    def __init__(
        self,
        agents: List[BaseAgent],
        min_score_threshold: float = 65.0,
        min_confidence_threshold: float = 50.0,
        run_parallel: bool = True,
    ) -> None:
        self.agents                   = agents
        self.min_score_threshold      = min_score_threshold
        self.min_confidence_threshold = min_confidence_threshold
        self.run_parallel             = run_parallel
        self._logger                  = get_logger("agents.voting_engine")

    async def vote(self, context: Dict[str, Any]) -> VoteResult:
        """اجرای همه Agentها و محاسبه رأی نهایی."""

        # اجرای موازی یا ترتیبی
        if self.run_parallel:
            results = await asyncio.gather(
                *[agent.run(context) for agent in self.agents],
                return_exceptions=False,
            )
        else:
            results = []
            for agent in self.agents:
                results.append(await agent.run(context))

        agent_results: List[AgentResult] = list(results)

        # بررسی Blocking Agents
        blocking_agents = [
            r.agent_name for r in agent_results
            if r.vote.status == AgentStatus.ERROR and r.vote.score == 0.0
        ]

        if blocking_agents:
            block_reasons = [
                r.vote.reason for r in agent_results
                if r.agent_name in blocking_agents
            ]
            self._logger.warning(f"Trade BLOCKED by: {blocking_agents}")
            return VoteResult(
                decision=TradeDecision.BLOCKED,
                final_score=0.0,
                final_confidence=0.0,
                weighted_score=0.0,
                agent_results=agent_results,
                votes_summary=self._build_summary(agent_results),
                blocking_agents=blocking_agents,
                direction=None,
                passed_threshold=False,
                threshold_used=self.min_score_threshold,
                total_weight=sum(a.weight for a in self.agents),
                reason=f"Blocked by: {' | '.join(block_reasons)}",
            )

        # محاسبه weighted score
        total_weighted_score = 0.0
        total_weight_conf    = 0.0
        direction_votes: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "NEUTRAL": 0.0}
        confidence_sum   = 0.0
        active_count     = 0

        for result in agent_results:
            vote   = result.vote
            agent  = next((a for a in self.agents if a.name == result.agent_name), None)
            weight = agent.weight if agent else 1.0

            if vote.status == AgentStatus.SKIP:
                continue

            conf_factor = vote.confidence / 100.0
            w_conf      = weight * conf_factor

            total_weighted_score += vote.score * w_conf
            total_weight_conf    += w_conf
            confidence_sum       += vote.confidence
            active_count         += 1

            # تجمیع رأی جهت
            direction = vote.direction or "NEUTRAL"
            direction_votes[direction] = direction_votes.get(direction, 0.0) + weight

        # محاسبه نهایی
        if total_weight_conf > 0:
            weighted_score    = total_weighted_score / total_weight_conf
        else:
            weighted_score    = 50.0

        avg_confidence = confidence_sum / active_count if active_count > 0 else 50.0

        # تعیین جهت نهایی
        direction_votes.pop("NEUTRAL", None)
        final_direction = max(direction_votes, key=direction_votes.get) if direction_votes else None
        if not direction_votes or max(direction_votes.values()) < 0.3:
            final_direction = None

        # تصمیم نهایی
        passed = (weighted_score >= self.min_score_threshold and
                  avg_confidence >= self.min_confidence_threshold)

        if passed and final_direction == "BUY":
            decision = TradeDecision.BUY
        elif passed and final_direction == "SELL":
            decision = TradeDecision.SELL
        else:
            decision = TradeDecision.NO_TRADE

        reason_parts = [f"Score={weighted_score:.1f}/{self.min_score_threshold}",
                        f"Conf={avg_confidence:.1f}/{self.min_confidence_threshold}",
                        f"Dir={final_direction}"]

        self._logger.info(
            f"Vote → {decision.value} | {' | '.join(reason_parts)}"
        )

        return VoteResult(
            decision=decision,
            final_score=weighted_score,
            final_confidence=avg_confidence,
            weighted_score=weighted_score,
            agent_results=agent_results,
            votes_summary=self._build_summary(agent_results),
            blocking_agents=[],
            direction=final_direction,
            passed_threshold=passed,
            threshold_used=self.min_score_threshold,
            total_weight=sum(a.weight for a in self.agents),
            reason=" | ".join(reason_parts),
        )

    def _build_summary(self, results: List[AgentResult]) -> Dict[str, Dict]:
        summary = {}
        for r in results:
            agent = next((a for a in self.agents if a.name == r.agent_name), None)
            summary[r.agent_name] = {
                "score":      r.vote.score,
                "confidence": r.vote.confidence,
                "weight":     agent.weight if agent else 0.0,
                "status":     r.vote.status.value,
                "reason":     r.vote.reason,
                "direction":  r.vote.direction,
                "elapsed_ms": round(r.elapsed_ms, 2),
            }
        return summary

    def update_weights(self, weight_map: Dict[str, float]) -> None:
        """بروزرسانی وزن‌ها از WeightAdjuster."""
        for agent in self.agents:
            if agent.name in weight_map:
                agent.weight = max(0.0, min(1.0, weight_map[agent.name]))
                self._logger.info(f"Weight updated: {agent.name} → {agent.weight:.3f}")

    def set_threshold(self, threshold: float) -> None:
        self.min_score_threshold = max(0.0, min(100.0, threshold))

    def enable_agent(self, name: str) -> None:
        for a in self.agents:
            if a.name == name:
                a.enabled = True

    def disable_agent(self, name: str) -> None:
        for a in self.agents:
            if a.name == name:
                a.enabled = False

    def get_weights(self) -> Dict[str, float]:
        return {a.name: a.weight for a in self.agents}
