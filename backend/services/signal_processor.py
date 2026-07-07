"""Signal Processor with Context Enrichment — Phase F.

Fixes BUG-F2: Context is now enriched with SMC, ML, and Session data
before being passed to VotingEngine. Agents receive real data.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.agents.voting_engine import (
    BaseAgent,
    FinalVote,
    VoteSignal,
    VotingConfig,
    VotingEngine,
)
from backend.services.context_enricher import ContextEnricher, get_context_enricher

logger = logging.getLogger(__name__)


class TradingSignal:
    """Lightweight signal produced by a route or strategy."""

    def __init__(
        self,
        symbol: str,
        direction: str,  # BUY | SELL | NEUTRAL
        confidence: float = 0.5,
        entry: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        rr: float = 0.0,
        source: str = "unknown",
        extra: Optional[Dict[str, Any]] = None,
        candles: Optional[List[Dict]] = None,
    ) -> None:
        self.symbol = symbol
        self.direction = direction.upper()
        self.confidence = float(confidence)
        self.entry = entry
        self.sl = sl
        self.tp = tp
        self.rr = float(rr)
        self.source = source
        self.extra = extra or {}
        self.candles = candles or []  # raw OHLCV list for SMCEngine

    def to_base_context(self) -> Dict[str, Any]:
        """Return minimal context dict — ContextEnricher will enrich it."""
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "confidence": self.confidence,
            "entry": self.entry,
            "sl": self.sl,
            "tp": self.tp,
            "rr": self.rr,
            "source": self.source,
            **self.extra,
        }


class SignalProcessor:
    """Orchestrates context enrichment and multi-agent voting."""

    def __init__(
        self,
        voting_config: Optional[VotingConfig] = None,
    ) -> None:
        self._voting_engine = VotingEngine(config=voting_config or VotingConfig())
        self._agents: List[BaseAgent] = []
        self._enricher: ContextEnricher = get_context_enricher()
        logger.info("[SignalProcessor] initialized")

    # ------------------------------------------------------------------
    # Engine injection (called from main.py lifespan)
    # ------------------------------------------------------------------

    def register_agents(self, agents: List[Any]) -> None:
        """Register agent instances with the VotingEngine."""
        self._agents = list(agents)
        logger.info(
            "[SignalProcessor] registered %d agents: %s",
            len(self._agents),
            [type(a).__name__ for a in self._agents],
        )

    def register_engines(
        self,
        smc_engine: Optional[Any] = None,
        ml_engine: Optional[Any] = None,
    ) -> None:
        """Inject real SMC and ML engines into the ContextEnricher.

        Call from lifespan() after startup:
            signal_processor.register_engines(
                smc_engine=smc_engine_instance,
                ml_engine=xgboost_trainer_instance,
            )
        """
        if smc_engine is not None:
            self._enricher.set_smc_engine(smc_engine)
        if ml_engine is not None:
            self._enricher.set_ml_engine(ml_engine)
        logger.info(
            "[SignalProcessor] engines registered smc=%s ml=%s",
            smc_engine is not None,
            ml_engine is not None,
        )

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------

    def process(
        self,
        signal: TradingSignal,
        candles: Optional[List[Dict]] = None,
    ) -> FinalVote:
        """Full pipeline: signal → enrich → vote → FinalVote.

        Args:
            signal:  The incoming trading signal.
            candles: Optional OHLCV list for SMCEngine analysis.
                     If not provided, signal.candles is used.

        Returns:
            FinalVote with signal (BUY/SELL/ABSTAIN), confidence, reason.
        """
        if not self._agents:
            logger.error("[SignalProcessor] no agents registered — call register_agents() first")
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason="no agents registered",
            )

        # Step 1: base context from signal
        base_ctx = signal.to_base_context()

        # Step 2: enrich — SMC, ML, Session
        raw_candles = candles or signal.candles
        enriched_ctx = self._enricher.enrich(base_ctx, candles=raw_candles)

        logger.debug(
            "[SignalProcessor] context enriched for %s/%s: session=%s bos=%s ml_prob=%.3f obs=%d",
            signal.symbol,
            signal.direction,
            enriched_ctx.get("session"),
            enriched_ctx.get("bos_detected"),
            enriched_ctx.get("ai_prediction", {}).get("probability", 0.0),
            len(enriched_ctx.get("order_blocks", [])),
        )

        # Step 3: vote
        final_vote = self._voting_engine.vote(self._agents, enriched_ctx)

        logger.info(
            "[SignalProcessor] %s/%s → %s (conf=%.2f) reason=%s",
            signal.symbol,
            signal.direction,
            final_vote.signal.value
            if hasattr(final_vote.signal, "value")
            else str(final_vote.signal),
            final_vote.confidence,
            final_vote.reason,
        )

        return final_vote

    # ------------------------------------------------------------------
    # Convenience: validate + process
    # ------------------------------------------------------------------

    def validate_and_process(
        self,
        signal: TradingSignal,
        candles: Optional[List[Dict]] = None,
    ) -> FinalVote:
        """Validate signal fields then process."""
        if not signal.symbol:
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason="invalid signal: missing symbol",
            )
        if signal.direction not in ("BUY", "SELL", "NEUTRAL"):
            return FinalVote(
                signal=VoteSignal.ABSTAIN,
                confidence=0.0,
                reason=f"invalid direction: {signal.direction}",
            )
        if not (0.0 <= signal.confidence <= 1.0):
            signal.confidence = max(0.0, min(1.0, signal.confidence))
        return self.process(signal, candles=candles)


# Module-level singleton
_processor: Optional[SignalProcessor] = None


def get_signal_processor() -> SignalProcessor:
    global _processor
    if _processor is None:
        _processor = SignalProcessor()
    return _processor


signal_processor: SignalProcessor = get_signal_processor()
