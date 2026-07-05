"""
ContextEnricher v3 — Phase H Fix

Fixes:
- BUG-H7: _enrich_ml_sync used asyncio.get_event_loop() which is deprecated
          in Python 3.10+ and raises RuntimeError in Python 3.12
          Fix: use asyncio.get_running_loop() with proper fallback
- BUG-G6: ML enrichment calls prediction_service.predict(context) async-safe
          instead of trainer.predict_proba(X) directly (kept from Phase G)
- ARCH: SMC layer, Session layer, ML layer all feed into context dict
        so every agent receives real data before voting
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Session schedule (UTC hours)
_SESSIONS: Dict[str, tuple] = {
    "SYDNEY":    (22, 7),
    "TOKYO":     (0,  9),
    "LONDON":    (7,  16),
    "NEW_YORK":  (12, 21),
}
_KILL_ZONES: Dict[str, tuple] = {
    "LONDON_OPEN":  (7,  9),
    "NY_OPEN":      (12, 14),
    "ASIA_OPEN":    (0,  2),
    "LONDON_CLOSE": (15, 17),
}
_SLIPPAGE_BY_SESSION: Dict[str, float] = {
    "LONDON":   0.5,
    "NEW_YORK": 0.8,
    "TOKYO":    1.2,
    "SYDNEY":   1.5,
}


class ContextEnricher:
    """
    Enriches a base context dict with 20+ keys before VotingEngine.
    Three enrichment layers:
      Layer 1 — Session: session name, kill zone, slippage
      Layer 2 — SMC:     order blocks, FVGs, BOS/CHOCH, bias, liquidity
      Layer 3 — ML:      ai_prediction probability & confidence
    """

    def __init__(
        self,
        smc_engine: Optional[Any] = None,
        ml_engine:  Optional[Any] = None,
    ) -> None:
        self._smc_engine = smc_engine
        self._ml_engine  = ml_engine
        logger.debug("[ContextEnricher] init smc=%s ml=%s",
                     type(smc_engine).__name__ if smc_engine else None,
                     type(ml_engine).__name__  if ml_engine  else None)

    def set_smc_engine(self, engine: Any) -> None:
        self._smc_engine = engine
        logger.info("[ContextEnricher] SMC engine registered: %s", type(engine).__name__)

    def set_ml_engine(self, engine: Any) -> None:
        self._ml_engine = engine
        logger.info("[ContextEnricher] ML engine registered: %s", type(engine).__name__)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def enrich(
        self,
        base_ctx: Dict[str, Any],
        candles: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Synchronous enrichment entry point used by SignalProcessor."""
        ctx = dict(base_ctx)
        self._enrich_session(ctx)
        self._enrich_smc(ctx, candles or [])
        self._enrich_ml_sync(ctx)   # BUG-H7 FIX: safe sync wrapper
        return ctx

    async def enrich_async(
        self,
        base_ctx: Dict[str, Any],
        candles: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Async enrichment — preferred when called from async context."""
        ctx = dict(base_ctx)
        self._enrich_session(ctx)
        self._enrich_smc(ctx, candles or [])
        await self._enrich_ml_async(ctx)
        return ctx

    # -----------------------------------------------------------------------
    # Layer 1 — Session
    # -----------------------------------------------------------------------

    def _enrich_session(self, ctx: Dict[str, Any]) -> None:
        now = datetime.now(timezone.utc)
        hour = now.hour

        # Detect active sessions
        active = [
            name for name, (s, e) in _SESSIONS.items()
            if (s <= e and s <= hour < e)
            or (s > e and (hour >= s or hour < e))
        ]
        session = active[0] if active else "OFF_HOURS"

        # Detect kill zone
        in_kz = any(
            s <= hour < e for s, e in _KILL_ZONES.values()
        )

        # London/NY overlap
        london_ny_overlap = 12 <= hour < 16

        ctx.update({
            "session":                 session,
            "active_sessions":         active,
            "in_kill_zone":            in_kz,
            "london_ny_overlap":       london_ny_overlap,
            "expected_slippage_pips":  _SLIPPAGE_BY_SESSION.get(session, 1.0),
            "hour_utc":                hour,
            "day_of_week":             now.weekday(),
            "session_score":           len(active) / 4.0,
        })

    # -----------------------------------------------------------------------
    # Layer 2 — SMC
    # -----------------------------------------------------------------------

    def _enrich_smc(self, ctx: Dict[str, Any], candles: List[Dict]) -> None:
        if self._smc_engine is None or not candles:
            ctx.setdefault("smc_analysis",    {})
            ctx.setdefault("order_blocks",    [])
            ctx.setdefault("fvgs",            [])
            ctx.setdefault("bos_detected",    False)
            ctx.setdefault("choch_detected",  False)
            ctx.setdefault("bias",            "NEUTRAL")
            ctx.setdefault("smc_confidence",  0.0)
            ctx.setdefault("liquidity_sweep", False)
            ctx.setdefault("htf_alignment",   False)
            ctx.setdefault("in_premium_zone", False)
            ctx.setdefault("in_discount_zone",False)
            ctx.setdefault("swing_high",      None)
            ctx.setdefault("swing_low",       None)
            ctx.setdefault("internal_liquidity", 0.0)
            ctx.setdefault("external_liquidity", 0.0)
            return

        try:
            result = self._smc_engine.analyse(candles)
            smc_data = result if isinstance(result, dict) else vars(result)

            ctx["smc_analysis"]    = smc_data
            ctx["order_blocks"]    = smc_data.get("order_blocks",   [])
            ctx["fvgs"]            = smc_data.get("fvgs",           [])
            ctx["bos_detected"]    = bool(smc_data.get("bos_detected",   False))
            ctx["choch_detected"]  = bool(smc_data.get("choch_detected", False))
            ctx["bias"]            = smc_data.get("bias",           "NEUTRAL")
            ctx["smc_confidence"]  = float(smc_data.get("confidence", 0.5))
            ctx["liquidity_sweep"] = bool(smc_data.get("liquidity_sweep", False))
            ctx["htf_alignment"]   = bool(smc_data.get("htf_alignment",  False))
            ctx["in_premium_zone"] = bool(smc_data.get("in_premium_zone",False))
            ctx["in_discount_zone"]= bool(smc_data.get("in_discount_zone",False))
            ctx["swing_high"]      = smc_data.get("swing_high")
            ctx["swing_low"]       = smc_data.get("swing_low")
            ctx["internal_liquidity"] = smc_data.get("internal_liquidity", 0.0)
            ctx["external_liquidity"] = smc_data.get("external_liquidity", 0.0)
        except Exception as exc:
            logger.warning("[ContextEnricher] SMCEngine.analyse() failed: %s", exc)
            self._enrich_smc(ctx, [])   # fill defaults

    # -----------------------------------------------------------------------
    # Layer 3 — ML  (BUG-G6 + BUG-H7 FIX)
    # -----------------------------------------------------------------------

    def _enrich_ml_sync(self, ctx: Dict[str, Any]) -> None:
        """
        BUG-H7 FIX: Previously used asyncio.get_event_loop() which is
        deprecated in Python 3.10+ and raises RuntimeError in 3.12.

        New approach:
          1. Try asyncio.get_running_loop() — if a loop is running, schedule
             the coroutine via run_coroutine_threadsafe (thread-safe).
          2. If no loop is running, create a temporary event loop to run once.
          3. On any failure, fill with empty prediction (fail-safe).
        """
        if self._ml_engine is None:
            # Try module-level prediction_service singleton
            try:
                from backend.ai_prediction.prediction_service import prediction_service as _ps
                if _ps._manager and _ps._manager.load_best_model() is not None:
                    self._ml_engine = _ps
            except Exception:
                pass

        if self._ml_engine is None:
            ctx["ai_prediction"] = self._empty_prediction("no ml engine")
            return

        try:
            # BUG-H7 FIX: use get_running_loop() not get_event_loop()
            try:
                loop = asyncio.get_running_loop()
                # We are inside an async context — use run_coroutine_threadsafe
                import concurrent.futures
                future = asyncio.run_coroutine_threadsafe(
                    self._enrich_ml_async(ctx), loop
                )
                future.result(timeout=2.0)
            except RuntimeError:
                # No running loop — safe to use asyncio.run()
                asyncio.run(self._enrich_ml_async(ctx))
        except Exception as exc:
            logger.warning("[ContextEnricher] ML enrichment failed: %s", exc)
            ctx["ai_prediction"] = self._empty_prediction(str(exc))

    async def _enrich_ml_async(self, ctx: Dict[str, Any]) -> None:
        """Async ML enrichment."""
        if self._ml_engine is None:
            ctx["ai_prediction"] = self._empty_prediction("no ml engine")
            return
        try:
            # PredictionService.predict(context)
            if hasattr(self._ml_engine, "predict") and asyncio.iscoroutinefunction(
                self._ml_engine.predict
            ):
                result = await self._ml_engine.predict(ctx)
                ctx["ai_prediction"] = (
                    result.to_dict() if hasattr(result, "to_dict") else dict(result)
                )
            # XGBoostTrainer.predict_proba(X) — direct trainer fallback
            elif hasattr(self._ml_engine, "predict_proba"):
                from backend.ai_prediction.feature_pipeline import build_features_from_context
                X = build_features_from_context(ctx)
                raw_prob = float(self._ml_engine.predict_proba(X)[0, 1])
                probability = int(round(raw_prob * 100))
                ctx["ai_prediction"] = {
                    "probability":   probability,
                    "confidence":    50 if probability >= 60 else 0,
                    "is_tradeable":  probability >= 60,
                    "model_auc":     0.60,
                    "risk":          "MEDIUM",
                    "reason":        f"direct trainer prob={probability}%",
                    "is_fallback":   False,
                }
            else:
                ctx["ai_prediction"] = self._empty_prediction("unknown engine type")
        except Exception as exc:
            logger.warning("[ContextEnricher] async ML enrichment failed: %s", exc)
            ctx["ai_prediction"] = self._empty_prediction(str(exc))

    @staticmethod
    def _empty_prediction(reason: str) -> Dict[str, Any]:
        return {
            "probability":   50,
            "confidence":    0,
            "is_tradeable":  False,
            "model_auc":     0.0,
            "risk":          "HIGH",
            "reason":        reason,
            "is_fallback":   True,
        }


# Module-level singleton
_enricher: Optional[ContextEnricher] = None


def get_context_enricher() -> ContextEnricher:
    global _enricher
    if _enricher is None:
        _enricher = ContextEnricher()
    return _enricher
