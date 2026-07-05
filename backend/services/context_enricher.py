"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Context Enricher — Phase J Fix

BUG-J4 FIX: _enrich_ml_sync() asyncio.get_event_loop() → Python 3.12 safe
  - try asyncio.get_running_loop() → run_coroutine_threadsafe()
  - except RuntimeError → asyncio.run() (new loop in thread)

وظیفه:
  پیش از VotingEngine ، context را با داده‌های لایه‌های:
    Layer 1: Session (Sydney/Tokyo/London/NewYork + kill_zone)
    Layer 2: SMCEngine (order_blocks, fvgs, BOS, CHOCH, liquidity)
    Layer 3: MLEngine (probability, confidence, model_auc)
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..core.logger import get_logger

logger = get_logger("services.context_enricher")


# ━━━ Session Detection ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_SESSION_HOURS = {
    "sydney":   (21, 6),
    "tokyo":    (0,  9),
    "london":   (7,  16),
    "new_york": (12, 21),
}
_KILL_ZONES = {
    "london_open":   (7,  9),
    "new_york_open": (12, 14),
    "london_close":  (14, 16),
    "tokyo_open":    (0,  2),
}
_SLIPPAGE_BY_SESSION = {
    "london":   0.3,
    "new_york": 0.5,
    "tokyo":    0.8,
    "sydney":   1.2,
    "off":      2.0,
}


def _detect_session(hour: int) -> str:
    active = []
    for name, (start, end) in _SESSION_HOURS.items():
        if start < end:
            if start <= hour < end:
                active.append(name)
        else:  # overnight
            if hour >= start or hour < end:
                active.append(name)
    if "london" in active and "new_york" in active:
        return "london_new_york_overlap"
    if active:
        return active[0]
    return "off"


def _detect_kill_zone(hour: int) -> Optional[str]:
    for name, (start, end) in _KILL_ZONES.items():
        if start <= hour < end:
            return name
    return None


# ━━━ ContextEnricher ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


class ContextEnricher:
    """
    پیش از VotingEngine، هر agent با context غنی دریافت می‌کند.

    استفاده:
        enricher = ContextEnricher()
        enricher.register_engines(smc_engine, ml_engine)
        enriched_ctx = await enricher.enrich(base_ctx, candles)
    """

    def __init__(self) -> None:
        self._smc_engine = None
        self._ml_engine  = None

    def register_engines(self, smc_engine=None, ml_engine=None) -> None:
        """inject engines from lifespan."""
        if smc_engine is not None:
            self._smc_engine = smc_engine
        if ml_engine is not None:
            self._ml_engine = ml_engine
        logger.info(
            "[ContextEnricher] engines registered: smc=%s ml=%s",
            self._smc_engine is not None,
            self._ml_engine is not None,
        )

    async def enrich(
        self,
        base_ctx: Dict[str, Any],
        candles: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        غنی‌سازی context با سه لایه.
        """
        ctx = dict(base_ctx)

        # Layer 1: Session
        ctx = self._enrich_session(ctx)

        # Layer 2: SMC
        if candles:
            ctx = await self._enrich_smc(ctx, candles)

        # Layer 3: ML
        ctx = await self._enrich_ml(ctx)

        return ctx

    # ━━━ Layer 1: Session ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _enrich_session(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        hour = now.hour
        session = _detect_session(hour)
        kill_zone = _detect_kill_zone(hour)
        slippage = _SLIPPAGE_BY_SESSION.get(session, 2.0)

        ctx.update({
            "session":                session,
            "in_kill_zone":           kill_zone is not None,
            "kill_zone_name":         kill_zone,
            "expected_slippage_pips": slippage,
            "hour_of_day":            hour,
            "day_of_week":            now.weekday(),
        })
        return ctx

    # ━━━ Layer 2: SMC ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _enrich_smc(
        self,
        ctx: Dict[str, Any],
        candles: List[Dict],
    ) -> Dict[str, Any]:
        if self._smc_engine is None:
            logger.debug("[ContextEnricher] SMCEngine not registered")
            return ctx
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _executor,
                lambda: self._smc_engine.analyse(candles),
            )
            ctx.update({
                "smc_analysis":       result,
                "order_blocks":       getattr(result, "order_blocks", []),
                "fvgs":               getattr(result, "fvgs", []),
                "bos_detected":       getattr(result, "bos_detected", False),
                "choch_detected":     getattr(result, "choch_detected", False),
                "swing_high":         getattr(result, "swing_high", 0.0),
                "swing_low":          getattr(result, "swing_low", 0.0),
                "bias":               getattr(result, "bias", "NEUTRAL"),
                "in_premium_zone":    getattr(result, "in_premium_zone", False),
                "in_discount_zone":   getattr(result, "in_discount_zone", False),
                "liquidity_sweep":    getattr(result, "liquidity_sweep", False),
                "internal_liquidity": getattr(result, "internal_liquidity", False),
                "htf_alignment":      getattr(result, "htf_alignment", False),
                "smc_confidence":     getattr(result, "confidence", 0.5),
            })
        except Exception as exc:
            logger.warning("[ContextEnricher] SMC enrich failed: %s", exc)
        return ctx

    # ━━━ Layer 3: ML ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _enrich_ml(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        if self._ml_engine is None:
            logger.debug("[ContextEnricher] MLEngine not registered")
            ctx.setdefault("ai_prediction", {"available": False, "probability": 0.5})
            return ctx
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                _executor,
                lambda: self._enrich_ml_sync(ctx),
            )
            ctx["ai_prediction"] = result
        except Exception as exc:
            logger.warning("[ContextEnricher] ML enrich failed: %s", exc)
            ctx.setdefault("ai_prediction", {"available": False, "probability": 0.5})
        return ctx

    def _enrich_ml_sync(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """
        BUG-J4 FIX: asyncio.get_event_loop() → Python 3.12 safe approach.

        رویکرد:
          1. try asyncio.get_running_loop() → اگر loop در حال اجرا باشد
             → future = asyncio.run_coroutine_threadsafe(coro, loop)
          2. except RuntimeError → در thread هیچ loop نیست
             → asyncio.run(coro) — loop جدید در thread
        """
        try:
            from backend.ai_prediction.prediction_service import prediction_service

            async def _predict():
                return await prediction_service.predict(ctx)

            try:
                loop = asyncio.get_running_loop()
                # در thread executor — لوپ اصلی در حال اجراست
                future = asyncio.run_coroutine_threadsafe(_predict(), loop)
                result = future.result(timeout=5.0)
            except RuntimeError:
                # در این thread هیچ loop وجود ندارد — loop جدید بساز
                result = asyncio.run(_predict())

            return {
                "available":   True,
                "probability": getattr(result, "probability", 0.5),
                "confidence":  getattr(result, "confidence", 0.5),
                "direction":   getattr(result, "direction", "NEUTRAL"),
                "model_auc":   getattr(result, "model_auc", 0.0),
            }
        except Exception as exc:
            logger.warning("[ContextEnricher] _enrich_ml_sync error: %s", exc)
            return {"available": False, "probability": 0.5, "confidence": 0.5}


# Singleton
context_enricher = ContextEnricher()
