"""
Context Enricher — Phase K Final
Pipeline: Session → SMC → ML → PriceAction → SMCScoring
All agents receive a fully populated context dict before voting.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── singleton engines (injected from lifespan) ───────────────────────────────
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
 """Called once from lifespan() with real engine instances."""
 global _smc_engine, _ml_engine, _pa_engine, _smc_scoring_engine
 _smc_engine = smc_engine
 _ml_engine = ml_engine
 _pa_engine = pa_engine
 _smc_scoring_engine = smc_scoring_engine
 logger.info(
 "ContextEnricher engines registered — "
 "smc=%s ml=%s pa=%s scoring=%s",
 smc_engine is not None,
 ml_engine is not None,
 pa_engine is not None,
 smc_scoring_engine is not None,
 )


# ── helpers ──────────────────────────────────────────────────────────────────
def _run_async_safely(coro):
 """Run a coroutine safely regardless of whether a loop is already running."""
 try:
 loop = asyncio.get_running_loop()
 # We are inside a running loop — schedule and wait via thread executor
 import concurrent.futures
 future = loop.run_in_executor(None, lambda: asyncio.run(coro))
 # This is called from a thread executor itself, so we can block
 return future.result(timeout=5)
 except RuntimeError:
 # No running loop — safe to call asyncio.run()
 return asyncio.run(coro)


# ── Layer 1: Session ──────────────────────────────────────────────────────────
def _enrich_session(ctx: Dict[str, Any]) -> Dict[str, Any]:
 """Detect current Forex session and kill zone status."""
 now_utc = datetime.now(timezone.utc)
 hour = now_utc.hour

 session = "off_hours"
 in_kill_zone = False
 expected_slippage_pips = 1.5

 if 22 <= hour or hour < 2:
 session = "sydney"
 expected_slippage_pips = 1.2
 elif 0 <= hour < 9:
 session = "tokyo"
 expected_slippage_pips = 1.0
 in_kill_zone = 1 <= hour <= 3
 elif 7 <= hour < 16:
 session = "london"
 expected_slippage_pips = 0.8
 in_kill_zone = 7 <= hour <= 9
 elif 13 <= hour < 22:
 session = "new_york"
 expected_slippage_pips = 0.9
 in_kill_zone = 13 <= hour <= 15

 ctx.update({
 "session": session,
 "in_kill_zone": in_kill_zone,
 "expected_slippage_pips": expected_slippage_pips,
 "session_hour_utc": hour,
 })
 return ctx


# ── Layer 2: SMC ─────────────────────────────────────────────────────────────
def _enrich_smc(ctx: Dict[str, Any], candles: List[Dict]) -> Dict[str, Any]:
 """Run SMCEngine.analyse() and populate all SMC context keys."""
 if _smc_engine is None or not candles:
 ctx.setdefault("order_blocks", [])
 ctx.setdefault("fvgs", [])
 ctx.setdefault("bias", "NEUTRAL")
 ctx.setdefault("bos_detected", False)
 ctx.setdefault("choch_detected", False)
 ctx.setdefault("swing_high", None)
 ctx.setdefault("swing_low", None)
 ctx.setdefault("in_premium_zone", False)
 ctx.setdefault("in_discount_zone", False)
 ctx.setdefault("liquidity_sweep", False)
 ctx.setdefault("internal_liquidity", False)
 ctx.setdefault("htf_alignment", "NEUTRAL")
 ctx.setdefault("smc_confidence", 0.0)
 ctx.setdefault("smc_analysis", {})
 return ctx

 try:
 result = _smc_engine.analyse(candles)
 smc_dict = result if isinstance(result, dict) else vars(result)

 ctx["order_blocks"] = smc_dict.get("order_blocks", [])
 ctx["fvgs"] = smc_dict.get("fair_value_gaps", smc_dict.get("fvgs", []))
 ctx["bias"] = smc_dict.get("bias", "NEUTRAL")
 ctx["bos_detected"] = bool(smc_dict.get("bos_detected", False))
 ctx["choch_detected"] = bool(smc_dict.get("choch_detected", False))
 ctx["swing_high"] = smc_dict.get("swing_high")
 ctx["swing_low"] = smc_dict.get("swing_low")
 ctx["in_premium_zone"] = bool(smc_dict.get("in_premium_zone", False))
 ctx["in_discount_zone"] = bool(smc_dict.get("in_discount_zone", False))
 ctx["liquidity_sweep"] = bool(smc_dict.get("liquidity_sweep", False))
 ctx["internal_liquidity"] = bool(smc_dict.get("internal_liquidity", False))
 ctx["htf_alignment"] = smc_dict.get("htf_alignment", "NEUTRAL")
 ctx["smc_confidence"] = float(smc_dict.get("confidence", 0.0))
 ctx["smc_analysis"] = smc_dict
 except Exception as exc:
 logger.warning("SMCEngine.analyse() failed: %s", exc)
 ctx.setdefault("smc_analysis", {})

 return ctx


# ── Layer 3: ML Prediction ────────────────────────────────────────────────────
def _enrich_ml_sync(ctx: Dict[str, Any]) -> Dict[str, Any]:
 """Run PredictionService.predict() synchronously from thread executor."""
 try:
 from backend.ai_prediction.prediction_service import prediction_service

 async def _predict():
 return await prediction_service.predict(ctx)

 try:
 loop = asyncio.get_running_loop()
 import concurrent.futures
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
 future = pool.submit(asyncio.run, _predict())
 result = future.result(timeout=5)
 except RuntimeError:
 result = asyncio.run(_predict())

 ai = result if isinstance(result, dict) else {}
 ctx["ai_prediction"] = {
 "probability": float(ai.get("probability", 0.0)),
 "confidence": float(ai.get("confidence", 0.0)),
 "direction": ai.get("direction", "NEUTRAL"),
 "model_auc": float(ai.get("model_auc", 0.0)),
 "available": bool(ai.get("available", False)),
 }
 except Exception as exc:
 logger.warning("ML enrichment failed: %s", exc)
 ctx["ai_prediction"] = {
 "probability": 0.0,
 "confidence": 0.0,
 "direction": "NEUTRAL",
 "model_auc": 0.0,
 "available": False,
 }
 return ctx


async def _enrich_ml(ctx: Dict[str, Any]) -> Dict[str, Any]:
 """Async wrapper — runs ML prediction in thread to avoid blocking event loop."""
 loop = asyncio.get_running_loop()
 import concurrent.futures
 with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
 ctx = await loop.run_in_executor(pool, _enrich_ml_sync, ctx)
 return ctx


# ── Layer 4: Price Action ─────────────────────────────────────────────────────
def _enrich_pa(ctx: Dict[str, Any], candles: List[Dict]) -> Dict[str, Any]:
 """Run PriceActionEngine.analyze() and populate PA context keys."""
 if _pa_engine is None or not candles:
 ctx.setdefault("pa_trend", "NEUTRAL")
 ctx.setdefault("pa_patterns", [])
 ctx.setdefault("pa_sr_levels", [])
 ctx.setdefault("pa_momentum", 0.0)
 ctx.setdefault("pa_volatility", 0.0)
 ctx.setdefault("pa_available", False)
 return ctx

 try:
 result = _pa_engine.analyze(candles)
 # PriceActionResult dataclass or dict
 if hasattr(result, "__dict__"):
 pa = vars(result)
 elif isinstance(result, dict):
 pa = result
 else:
 pa = {}

 # Normalise trend to string
 trend_raw = pa.get("trend", "NEUTRAL")
 trend_str = trend_raw.value if hasattr(trend_raw, "value") else str(trend_raw)

 ctx["pa_trend"] = trend_str
 ctx["pa_patterns"] = pa.get("patterns", [])
 ctx["pa_sr_levels"] = pa.get("support_resistance", pa.get("sr_levels", []))
 ctx["pa_momentum"] = float(pa.get("momentum", 0.0))
 ctx["pa_volatility"] = float(pa.get("volatility", pa.get("atr", 0.0)))
 ctx["pa_available"] = True
 ctx["pa_result"] = pa # full result for agents that need it

 logger.debug(
 "PA enrichment: trend=%s patterns=%d sr_levels=%d",
 trend_str,
 len(ctx["pa_patterns"]),
 len(ctx["pa_sr_levels"]),
 )
 except Exception as exc:
 logger.warning("PriceActionEngine.analyze() failed: %s", exc)
 ctx.setdefault("pa_trend", "NEUTRAL")
 ctx.setdefault("pa_patterns", [])
 ctx.setdefault("pa_sr_levels", [])
 ctx.setdefault("pa_momentum", 0.0)
 ctx.setdefault("pa_volatility", 0.0)
 ctx.setdefault("pa_available", False)

 return ctx


# ── Layer 5: SMC Scoring ──────────────────────────────────────────────────────
def _enrich_smc_scoring(ctx: Dict[str, Any]) -> Dict[str, Any]:
 """Run SMCScoringEngine.score() using already-populated SMC context."""
 if _smc_scoring_engine is None:
 ctx.setdefault("smc_score", 0.0)
 ctx.setdefault("smc_quality", "POOR")
 ctx.setdefault("smc_components", {})
 return ctx

 try:
 # Pass full smc_analysis dict to scoring engine
 smc_data = ctx.get("smc_analysis", {})
 if not smc_data:
 # Build minimal smc_data from individual context keys
 smc_data = {
 "order_blocks": ctx.get("order_blocks", []),
 "fair_value_gaps": ctx.get("fvgs", []),
 "bias": ctx.get("bias", "NEUTRAL"),
 "bos_detected": ctx.get("bos_detected", False),
 "choch_detected": ctx.get("choch_detected", False),
 "liquidity_sweep": ctx.get("liquidity_sweep", False),
 "in_discount_zone": ctx.get("in_discount_zone", False),
 "in_premium_zone": ctx.get("in_premium_zone", False),
 "htf_alignment": ctx.get("htf_alignment", "NEUTRAL"),
 }

 score_result = _smc_scoring_engine.score(smc_data)
 if isinstance(score_result, dict):
 sr = score_result
 else:
 sr = vars(score_result)

 ctx["smc_score"] = float(sr.get("score", 0.0))
 ctx["smc_quality"] = sr.get("quality", "POOR")
 ctx["smc_components"] = sr.get("components", {})

 logger.debug(
 "SMCScoring: score=%.1f quality=%s",
 ctx["smc_score"],
 ctx["smc_quality"],
 )
 except Exception as exc:
 logger.warning("SMCScoringEngine.score() failed: %s", exc)
 ctx.setdefault("smc_score", 0.0)
 ctx.setdefault("smc_quality", "POOR")
 ctx.setdefault("smc_components", {})

 return ctx


# ── Main Entry Point ──────────────────────────────────────────────────────────
async def enrich(
 base_ctx: Dict[str, Any],
 candles: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
 """
 Full 5-layer enrichment pipeline.
 Layers: Session → SMC → ML → PriceAction → SMCScoring
 """
 ctx = dict(base_ctx) # defensive copy
 _candles = candles or []

 # Layer 1 — Session (sync, fast)
 ctx = _enrich_session(ctx)

 # Layer 2 — SMC (sync, CPU-bound)
 ctx = _enrich_smc(ctx, _candles)

 # Layer 3 — ML (async, I/O-bound)
 ctx = await _enrich_ml(ctx)

 # Layer 4 — Price Action (sync, CPU-bound)
 ctx = _enrich_pa(ctx, _candles)

 # Layer 5 — SMC Scoring (sync, uses Layer 2 output)
 ctx = _enrich_smc_scoring(ctx)

 return ctx


async def enrich_async(
 base_ctx: Dict[str, Any],
 candles: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
 """Alias for enrich() — backward compatibility."""
 return await enrich(base_ctx, candles)


# ── Singleton accessor ────────────────────────────────────────────────────────
class ContextEnricher:
 """Thin wrapper exposing enrich() as a class method for injection."""

 async def enrich(
 self,
 base_ctx: Dict[str, Any],
 candles: Optional[List[Dict]] = None,
 ) -> Dict[str, Any]:
 return await enrich(base_ctx, candles)

 def register_engines(self, **kwargs) -> None:
 register_engines(**kwargs)


_enricher_instance: Optional[ContextEnricher] = None


def get_enricher() -> ContextEnricher:
 global _enricher_instance
 if _enricher_instance is None:
 _enricher_instance = ContextEnricher()
 return _enricher_instance
