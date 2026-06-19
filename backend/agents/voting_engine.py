"""Galaxy Vast AI Trading Platform
VotingEngine - Multi-Agent Weighted Voting System

Fixes applied:
- MEDIUM: Only warned when weights != 1.0 → now auto-normalizes at __init__
- LOW: _run_agent_safe was @staticmethod but internally it's called as instance → kept static, fixed call pattern
- LOW: direction_votes default had 'NEUTRAL' but direction from agents can be anything → normalize via setdefault
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .base_agent import AgentResult, AgentStatus, AgentVote, BaseAgent
from backend.core.logger import get_logger

logger = get_logger('agents.voting_engine')


class VoteDecision(str, Enum):
    BUY      = 'BUY'
    SELL     = 'SELL'
    NO_TRADE = 'NO_TRADE'
    BLOCKED  = 'BLOCKED'


@dataclass
class VoteResult:
    decision:       VoteDecision
    weighted_score: float
    confidence:     float           # primary confidence field
    direction:      str
    agent_results:  List[AgentResult]  = field(default_factory=list)
    blocked_by:     Optional[str]      = None
    reasons:        List[str]          = field(default_factory=list)
    elapsed_ms:     float              = 0.0
    metadata:       Dict[str, Any]     = field(default_factory=dict)

    @property
    def final_confidence(self) -> float:
        """Alias for confidence — used by decision_service.py"""
        return self.confidence

    @property
    def passed_threshold(self) -> bool:
        """True when decision is BUY or SELL (not NO_TRADE / BLOCKED)"""
        return self.decision in (VoteDecision.BUY, VoteDecision.SELL)

    @property
    def blocking_agents(self) -> List[str]:
        """List of agent names that issued a BLOCKED vote"""
        return (
            [self.blocked_by]
            if self.blocked_by
            else [
                r.agent_name
                for r in self.agent_results
                if r.vote.status == AgentStatus.ERROR and r.vote.score == 0.0
            ]
        )

    @property
    def votes_summary(self) -> Dict[str, Any]:
        """Per-agent vote summary dict used by decision_service.py"""
        return {
            r.agent_name: {
                'score':     round(r.vote.score, 2),
                'direction': r.vote.direction,
                'status':    r.vote.status.value,
                'reason':    r.vote.reason,
            }
            for r in self.agent_results
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            'decision':         self.decision.value,
            'weighted_score':   round(self.weighted_score, 2),
            'confidence':       round(self.confidence, 2),
            'final_confidence': round(self.confidence, 2),
            'direction':        self.direction,
            'blocked_by':       self.blocked_by,
            'blocking_agents':  self.blocking_agents,
            'passed_threshold': self.passed_threshold,
            'reasons':          self.reasons,
            'elapsed_ms':       round(self.elapsed_ms, 1),
            'votes_summary':    self.votes_summary,
            'agents': [
                {
                    'name':       r.agent_name,
                    'score':      round(r.vote.score, 2),
                    'confidence': round(r.vote.confidence, 2),
                    'direction':  r.vote.direction,
                    'status':     r.vote.status.value,
                    'reason':     r.vote.reason,
                    'elapsed_ms': round(r.elapsed_ms, 1),
                }
                for r in self.agent_results
            ],
            **self.metadata,
        }


class VotingEngine:
    """Multi-Agent Weighted Voting Engine."""

    def __init__(
        self,
        agents:                      List[BaseAgent],
        min_score_threshold:         float = 65.0,
        min_confidence_threshold:    float = 50.0,
        run_parallel:                bool  = True,
    ) -> None:
        self._agents                    = agents
        self._min_score_threshold       = min_score_threshold
        self._min_confidence_threshold  = min_confidence_threshold
        self._run_parallel              = run_parallel

        # Auto-normalize weights if they don't sum to 1.0
        enabled = [a for a in agents if a.enabled]
        if enabled:
            total_weight = sum(a.weight for a in enabled)
            if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
                logger.warning(
                    'Agent weights sum=%.4f (expected ~1.0) — auto-normalizing.',
                    total_weight,
                )
                for a in enabled:
                    a.weight = a.weight / total_weight
                logger.info('Weights normalized. New map: %s',
                            {a.name: round(a.weight, 4) for a in enabled})

        logger.info(
            'VotingEngine ready | %d agents | parallel=%s | '
            'min_score=%s min_conf=%s',
            len(agents), run_parallel,
            min_score_threshold, min_confidence_threshold,
        )

    # ────────────────────────────────────────────────────────────── #
    # Public API                                                            #
    # ────────────────────────────────────────────────────────────── #

    async def vote(self, context: Dict[str, Any]) -> VoteResult:
        t0 = time.perf_counter()
        if self._run_parallel:
            agent_results = await self._run_parallel_safe(context)
        else:
            agent_results = await self._run_sequential_safe(context)
        result = self._aggregate(agent_results)
        result.elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            'Vote: %s score=%.1f conf=%.1f [%.0fms]',
            result.decision.value, result.weighted_score,
            result.confidence, result.elapsed_ms,
        )
        return result

    def update_weights(self, weight_map: Dict[str, float]) -> None:
        """Update agent weights at runtime."""
        for agent in self._agents:
            if agent.name in weight_map:
                agent.weight = float(weight_map[agent.name])
        # Re-normalize after update
        enabled = [a for a in self._agents if a.enabled]
        total = sum(a.weight for a in enabled)
        if total > 0 and abs(total - 1.0) > 0.01:
            for a in enabled:
                a.weight = a.weight / total
        logger.info('VotingEngine weights updated: %s', weight_map)

    def set_threshold(self, threshold: float) -> None:
        self._min_score_threshold = float(threshold)
        logger.info('VotingEngine threshold updated: %s', threshold)

    def enable_agent(self, name: str) -> None:
        for agent in self._agents:
            if agent.name == name:
                agent.enabled = True
                logger.info('Agent enabled: %s', name)
                return
        logger.warning('enable_agent: agent not found: %s', name)

    def disable_agent(self, name: str) -> None:
        for agent in self._agents:
            if agent.name == name:
                agent.enabled = False
                logger.info('Agent disabled: %s', name)
                return
        logger.warning('disable_agent: agent not found: %s', name)

    def get_weights(self) -> Dict[str, float]:
        return {a.name: a.weight for a in self._agents}

    @property
    def agents(self) -> List[BaseAgent]:
        return self._agents

    # ────────────────────────────────────────────────────────────── #
    # Internal                                                              #
    # ────────────────────────────────────────────────────────────── #

    async def _run_parallel_safe(self, context: Dict[str, Any]) -> List[AgentResult]:
        tasks = [self._run_agent_safe(a, context) for a in self._agents]
        raw   = await asyncio.gather(*tasks, return_exceptions=True)
        results: List[AgentResult] = []
        for i, item in enumerate(raw):
            if isinstance(item, BaseException):
                name = self._agents[i].name if i < len(self._agents) else f'Agent[{i}]'
                logger.error('Gather exception for %s: %s', name, item)
                results.append(AgentResult(
                    agent_name=name,
                    vote=AgentVote(score=50.0, confidence=0.0,
                                   status=AgentStatus.ERROR,
                                   reason=f'Unexpected: {item}'),
                    elapsed_ms=0.0, error=str(item),
                ))
            else:
                results.append(item)
        return results

    async def _run_sequential_safe(self, context: Dict[str, Any]) -> List[AgentResult]:
        results: List[AgentResult] = []
        for agent in self._agents:
            results.append(await self._run_agent_safe(agent, context))
        return results

    @staticmethod
    async def _run_agent_safe(agent: BaseAgent, context: Dict[str, Any]) -> AgentResult:
        try:
            return await agent.run(context)
        except Exception as exc:
            logger.error("Agent '%s' fatal error: %s", agent.name, exc, exc_info=True)
            return AgentResult(
                agent_name=agent.name,
                vote=AgentVote(score=50.0, confidence=0.0,
                               status=AgentStatus.ERROR,
                               reason=f'Fatal: {exc}'),
                elapsed_ms=0.0, error=str(exc),
            )

    def _aggregate(self, results: List[AgentResult]) -> VoteResult:
        for r in results:
            if r.vote.status == AgentStatus.ERROR and r.vote.score == 0.0:
                logger.warning("BLOCKED by '%s': %s", r.agent_name, r.vote.reason)
                return VoteResult(
                    decision=VoteDecision.BLOCKED, weighted_score=0.0,
                    confidence=0.0, direction='BLOCKED',
                    agent_results=results, blocked_by=r.agent_name,
                    reasons=[f'Blocked by {r.agent_name}: {r.vote.reason}'],
                )
        total_weight    = 0.0
        weighted_sum    = 0.0
        weighted_conf   = 0.0
        # Use setdefault so unknown directions don't raise KeyError
        direction_votes: Dict[str, float] = {'BUY': 0.0, 'SELL': 0.0, 'NEUTRAL': 0.0}
        reasons: List[str] = []
        agent_weights = {a.name: a.weight for a in self._agents}
        for r in results:
            weight = agent_weights.get(r.agent_name, 1.0 / max(len(results), 1))
            if r.vote.status == AgentStatus.SKIP:
                continue
            if r.vote.status == AgentStatus.ERROR:
                weight *= 0.5
            weighted_sum   += r.vote.score      * weight
            weighted_conf  += r.vote.confidence * weight
            total_weight   += weight
            direction = (r.vote.direction or 'NEUTRAL').upper()
            direction_votes.setdefault(direction, 0.0)   # handle unknown directions
            direction_votes[direction] += weight
            if r.vote.reason:
                reasons.append(f'[{r.agent_name}] {r.vote.reason}')
        if total_weight > 0:
            weighted_score = weighted_sum  / total_weight
            confidence     = weighted_conf / total_weight
        else:
            weighted_score, confidence = 50.0, 0.0
        weighted_score = max(0.0, min(100.0, weighted_score))
        confidence     = max(0.0, min(100.0, confidence))
        direction = max(direction_votes, key=lambda d: direction_votes[d])
        score_ok = weighted_score >= self._min_score_threshold
        conf_ok  = confidence     >= self._min_confidence_threshold
        if score_ok and conf_ok:
            decision = VoteDecision.BUY if direction == 'BUY' else (
                VoteDecision.SELL if direction == 'SELL' else VoteDecision.NO_TRADE
            )
        else:
            decision = VoteDecision.NO_TRADE
            reasons.append(
                f'Threshold not met: score={weighted_score:.1f}/{self._min_score_threshold} '
                f'conf={confidence:.1f}/{self._min_confidence_threshold}'
            )
        return VoteResult(
            decision=decision,
            weighted_score=weighted_score,
            confidence=confidence,
            direction=direction,
            agent_results=results,
            reasons=reasons,
            metadata={
                'direction_votes': direction_votes,
                'total_weight':    round(total_weight, 4),
                'active_agents':   len([r for r in results if r.vote.status != AgentStatus.SKIP]),
                'error_agents':    len([r for r in results if r.vote.status == AgentStatus.ERROR]),
            },
        )
