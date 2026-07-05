"""
Decision Engine — Phase A Fix
ARCH-R6-2: Was standalone — now exposes get_final_signal() for SignalProcessor.
Integrates SMC + Price Action + ML votes into a weighted final decision.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class EngineVote:
    source: str          # "SMC" | "PA" | "ML"
    signal: str          # "BUY" | "SELL" | "NO_TRADE"
    confidence: float    # 0.0 – 1.0
    reason: str = ""


@dataclass
class FinalDecision:
    signal: str          # "BUY" | "SELL" | "NO_TRADE"
    confidence: float
    votes: list
    reason: str
    approved: bool       # True if confidence >= min_confidence


class DecisionEngine:
    """
    Aggregates votes from SMC, Price Action, and ML engines into a
    single weighted final decision.

    Phase A Fix: get_final_signal() added so SignalProcessor can call
    this as an additional validation gate before VotingEngine.
    """

    # Weights for each source
    WEIGHTS: Dict[str, float] = {
        "SMC": 1.0,
        "PA":  1.0,
        "ML":  1.5,    # ML gets higher weight (data-driven)
        "NEWS": 0.5,
    }

    def __init__(
        self,
        min_confidence: float = 0.55,
        require_agreement: bool = False,
    ) -> None:
        """
        Args:
            min_confidence: minimum weighted confidence to approve a signal.
            require_agreement: if True, all non-abstaining sources must agree.
        """
        self._min_confidence = min_confidence
        self._require_agreement = require_agreement

    def decide(self, votes: list) -> FinalDecision:
        """
        Aggregate EngineVote list into FinalDecision.

        Algorithm:
        1. Group votes by signal (BUY/SELL/NO_TRADE)
        2. Weighted score per group: sum(weight * confidence)
        3. Winner = highest weighted score
        4. Approved if winner_score / total_weight >= min_confidence
        """
        if not votes:
            return FinalDecision(
                signal="NO_TRADE",
                confidence=0.0,
                votes=[],
                reason="No votes provided",
                approved=False,
            )

        scores: Dict[str, float] = {"BUY": 0.0, "SELL": 0.0, "NO_TRADE": 0.0}
        total_weight = 0.0
        vote_summaries = []

        for vote in votes:
            w = self.WEIGHTS.get(vote.source, 1.0)
            scores[vote.signal] = scores.get(vote.signal, 0.0) + w * vote.confidence
            total_weight += w
            vote_summaries.append({
                "source": vote.source,
                "signal": vote.signal,
                "confidence": vote.confidence,
                "reason": vote.reason,
            })

        if total_weight == 0:
            return FinalDecision(
                signal="NO_TRADE",
                confidence=0.0,
                votes=vote_summaries,
                reason="Zero total weight",
                approved=False,
            )

        # Winner by weighted score
        winner = max(scores, key=lambda s: scores[s])
        winner_score = scores[winner]
        confidence = winner_score / total_weight

        # Require agreement check
        if self._require_agreement:
            active_signals = {v.signal for v in votes if v.signal != "NO_TRADE"}
            if len(active_signals) > 1:
                return FinalDecision(
                    signal="NO_TRADE",
                    confidence=confidence,
                    votes=vote_summaries,
                    reason=f"Sources disagree: {active_signals}",
                    approved=False,
                )

        approved = confidence >= self._min_confidence and winner != "NO_TRADE"

        logger.debug(
            "[DecisionEngine] signal=%s confidence=%.3f approved=%s scores=%s",
            winner, confidence, approved, scores
        )

        return FinalDecision(
            signal=winner,
            confidence=confidence,
            votes=vote_summaries,
            reason=(
                f"Weighted scores: BUY={scores['BUY']:.2f} "
                f"SELL={scores['SELL']:.2f} "
                f"NO_TRADE={scores['NO_TRADE']:.2f}"
            ),
            approved=approved,
        )

    def get_final_signal(
        self,
        smc_result: Optional[Dict[str, Any]] = None,
        pa_result: Optional[Dict[str, Any]] = None,
        ml_result: Optional[Dict[str, Any]] = None,
        news_result: Optional[Dict[str, Any]] = None,
    ) -> FinalDecision:
        """
        Phase A Fix: Public interface for SignalProcessor integration.

        Converts raw engine result dicts to EngineVote objects and
        delegates to decide().

        Args:
            smc_result:  dict with keys 'signal', 'confidence', 'reason'
            pa_result:   same structure
            ml_result:   same structure
            news_result: same structure

        Returns:
            FinalDecision
        """
        votes = []

        for source, result in [
            ("SMC", smc_result),
            ("PA", pa_result),
            ("ML", ml_result),
            ("NEWS", news_result),
        ]:
            if result is None:
                continue
            try:
                votes.append(EngineVote(
                    source=source,
                    signal=str(result.get("signal", "NO_TRADE")).upper(),
                    confidence=float(result.get("confidence", 0.0)),
                    reason=str(result.get("reason", "")),
                ))
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "[DecisionEngine] Could not parse %s result: %s — %s",
                    source, result, exc
                )

        return self.decide(votes)


# Module-level singleton
decision_engine = DecisionEngine()
