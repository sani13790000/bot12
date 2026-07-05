"""
Signal Processor — Phase K Final
Routes TradingSignal through 5-layer context enrichment then VotingEngine.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# engines injected from lifespan
_smc_engine = None
_ml_engine = None
_pa_engine = None
_smc_scoring_engine = None


def register_engines(
 smc_engine=None,
 ml_engine=None,
 pa_engine=None,
 smc_scoring_engine=None,
) -> None:
 global _smc_engine, _ml_engine, _pa_engine, _smc_scoring_engine
 _smc_engine = smc_engine
 _ml_engine = ml_engine
 _pa_engine = pa_engine
 _smc_scoring_engine = smc_scoring_engine
 logger.info(
 "SignalProcessor engines registered — smc=%s ml=%s pa=%s scoring=%s",
 smc_engine is not None,
 ml_engine is not None,
 pa_engine is not None,
 smc_scoring_engine is not None,
 )


class SignalProcessor:
 """
 Validates an incoming TradingSignal, enriches context (5 layers),
 runs VotingEngine, and returns a ProcessedSignal.
 """

 def __init__(self):
 from backend.agents.voting_engine import VotingEngine
 self._voting = VotingEngine()

 def register_engines(self, **kwargs) -> None:
 """Instance-level proxy — delegates to module-level register_engines."""
 register_engines(**kwargs)

 async def process(
 self,
 signal,
 candles: Optional[List[Dict]] = None,
 ) -> Dict[str, Any]:
 """
 Full pipeline:
 1. Validate signal
 2. Build base context from signal fields
 3. Enrich context (5 layers: Session, SMC, ML, PA, SMCScoring)
 4. Run VotingEngine
 5. Return ProcessedSignal dict
 """
 # — 1. Basic validation —
 if not self._validate(signal):
 return self._rejected(signal, "validation_failed")

 # — 2. Base context —
 base_ctx: Dict[str, Any] = {
 "symbol": getattr(signal, "symbol", "XAUUSD"),
 "direction": getattr(signal, "direction", "NEUTRAL"),
 "confidence": float(getattr(signal, "confidence", 0.0)),
 "rr": float(getattr(signal, "rr", 0.0)),
 "entry": float(getattr(signal, "entry", 0.0)),
 "sl": float(getattr(signal, "sl", 0.0)),
 "tp": float(getattr(signal, "tp", 0.0)),
 "timeframe": getattr(signal, "timeframe", "H1"),
 }

 # — 3. Enrich context (5 layers incl. PA + SMCScoring) —
 _candles = candles or []
 try:
 from backend.services.context_enricher import enrich
 ctx = await enrich(base_ctx, _candles)
 except Exception as exc:
 logger.warning("Context enrichment failed, using base_ctx: %s", exc)
 ctx = base_ctx

 # — 4. VotingEngine —
 try:
 vote_result = await self._voting.vote(ctx)
 except Exception as exc:
 logger.warning("VotingEngine failed: %s", exc)
 vote_result = {"decision": "NO_TRADE", "score": 0, "reason": str(exc)}

 # — 5. Build ProcessedSignal —
 return {
 "signal": base_ctx,
 "context": ctx,
 "vote": vote_result,
 "decision": vote_result.get("decision", "NO_TRADE"),
 "pa_trend": ctx.get("pa_trend", "NEUTRAL"),
 "pa_patterns": ctx.get("pa_patterns", []),
 "smc_score": ctx.get("smc_score", 0.0),
 "smc_quality": ctx.get("smc_quality", "POOR"),
 "ai_probability": ctx.get("ai_prediction", {}).get("probability", 0.0),
 }

 def _validate(self, signal) -> bool:
 required = ["symbol", "direction", "entry", "sl", "tp"]
 for attr in required:
 if not hasattr(signal, attr):
 logger.warning("Signal missing attribute: %s", attr)
 return False
 rr = float(getattr(signal, "rr", 0))
 if rr < 1.5:
 logger.warning("Signal RR too low: %.2f", rr)
 return False
 return True

 def _rejected(self, signal, reason: str) -> Dict[str, Any]:
 return {
 "signal": {"symbol": getattr(signal, "symbol", "?")},
 "context": {},
 "vote": {"decision": "NO_TRADE"},
 "decision": "NO_TRADE",
 "rejection_reason": reason,
 }


# singleton
signal_processor = SignalProcessor()
