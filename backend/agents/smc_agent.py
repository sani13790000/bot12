"""backend/agents/smc_agent.py
SMC (Smart Money Concept) Analysis Agent.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from .base_agent import BaseAgent, AgentResult, AgentStatus, AgentVote, VoteSignal
from ..analysis.smc_scoring import SMCScorer

logger = logging.getLogger(__name__)


class SMCAgent(BaseAgent):
    """Analyzes Smart Money Concepts for trading signals."""

    agent_id = "smc_agent"
    weight = 1.5

    def __init__(self):
        super().__init__()
        self._scorer = SMCScorer()

    async def analyze(self, context: Dict[str, Any]) -> AgentResult:
        """Run SMC analysis and return vote."""
        try:
            candles = context.get("candles", [])
            symbol = context.get("symbol", "XAUUSD")

            if not candles:
                return AgentResult(
                    agent_id=self.agent_id,
                    status=AgentStatus.SKIPPED,
                    vote=AgentVote(
                        agent_id=self.agent_id,
                        signal=VoteSignal.ABSTAIN,
                        confidence=0.0,
                        weight=self.weight,
                        reason="no candles provided",
                    ),
                )

            score = await self._scorer.score(candles, symbol)

            if score.total_score >= 70:
                signal = VoteSignal.BUY if score.bias == "bullish" else VoteSignal.SELL
            elif score.total_score <= 30:
                signal = VoteSignal.SELL if score.bias == "bullish" else VoteSignal.BUY
            else:
                signal = VoteSignal.HOLD

            confidence = min(score.total_score / 100.0, 1.0)

            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.OK,
                vote=AgentVote(
                    agent_id=self.agent_id,
                    signal=signal,
                    confidence=confidence,
                    weight=self.weight,
                    reason=f"SMC score={score.total_score:.1f} bias={score.bias}",
                ),
            )
        except Exception as e:
            logger.error(f"SMCAgent.analyze error: {e}")
            return AgentResult(
                agent_id=self.agent_id,
                status=AgentStatus.ERROR,
                vote=AgentVote(
                    agent_id=self.agent_id,
                    signal=VoteSignal.ABSTAIN,
                    confidence=0.0,
                    weight=self.weight,
                    reason=f"error: {e}",
                    error=str(e),
                ),
            )
