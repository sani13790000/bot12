"""Context Enrichment Pipeline — Phase F Fix.

This module runs SMCEngine, PredictionService, and SessionManager
BEFORE the VotingEngine receives the context dict.

Previous problem: All agents called context.get('smc_analysis', {})
but no code ever PUT smc_analysis into context. Same for ai_prediction,
session, liquidity_sweep, bos_detected, etc.

This module fixes that by building a rich context dict from real engines.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SESSIONS = {
    "sydney":   (21, 6),
    "tokyo":    (0,  9),
    "london":   (7,  16),
    "new_york": (12, 21),
}

_KILL_ZONES = {
    "london_open":   (7,  9),
    "new_york_open": (12, 14),
    "london_close":  (15, 16),
    "asian_session": (0,  4),
}

_HIGH_IMPACT_PAIRS = {"EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "USDCHF"}


def _get_session_context(symbol: str) -> Dict[str, Any]:
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    active_sessions: List[str] = []
    for name, (start, end) in _SESSIONS.items():
        if start > end:
            if hour >= start or hour < end:
                active_sessions.append(name)
        elif start <= hour < end:
            active_sessions.append(name)
    primary_session = active_sessions[0] if active_sessions else "off_hours"
    in_kill_zone = False
    kill_zone_name = ""
    for name, (start, end) in _KILL_ZONES.items():
        if start <= hour < end:
            in_kill_zone = True
            kill_zone_name = name
            break
    base_slippage = 2.0
    if in_kill_zone:
        base_slippage = 1.0
    elif primary_session == "off_hours":
        base_slippage = 5.0
    if symbol.upper() in _HIGH_IMPACT_PAIRS:
        base_slippage *= 0.8
    return {
        "session": primary_session,
        "active_sessions": active_sessions,
        "in_kill_zone": in_kill_zone,
        "kill_zone_name": kill_zone_name,
        "expected_slippage_pips": round(base_slippage, 1),
        "trading_hour_utc": hour,
    }


def _ob_to_dict(ob: Any) -> Dict:
    if isinstance(ob, dict):
        return ob
    return {
        "high": getattr(ob, "high", 0),
        "low": getattr(ob, "low", 0),
        "direction": getattr(ob, "direction", "NEUTRAL"),
        "strength": getattr(ob, "strength", 0.5),
        "mitigated": getattr(ob, "mitigated", False),
    }


def _fvg_to_dict(fvg: Any) -> Dict:
    if isinstance(fvg, dict):
        return fvg
    return {
        "high": getattr(fvg, "high", 0),
        "low": getattr(fvg, "low", 0),
        "direction": getattr(fvg, "direction", "NEUTRAL"),
        "filled": getattr(fvg, "filled", False),
    }


def _liq_to_dict(liq: Any) -> Dict:
    if isinstance(liq, dict):
        return liq
    return {
        "level": getattr(liq, "level", 0),
        "type": getattr(liq, "type", "equal_high"),
        "swept": getattr(liq, "swept", False),
    }


def _extract_smc_context(
    smc_result: Optional[Any],
    candles: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    if smc_result is None:
        return {
            "smc_analysis": {},
            "order_blocks": [],
            "fvgs": [],
            "liquidity_levels": [],
            "swing_high": None,
            "swing_low": None,
            "bias": "NEUTRAL",
            "premium_zone": None,
            "discount_zone": None,
            "in_premium_zone": False,
            "in_discount_zone": False,
            "liquidity_sweep": False,
            "internal_liquidity": False,
            "bos_detected": False,
            "choch_detected": False,
            "htf_alignment": "NEUTRAL",
            "smc_confidence": 0.0,
        }
    obs  = getattr(smc_result, "order_blocks", []) or []
    fvgs = getattr(smc_result, "fair_value_gaps", []) or []
    liq  = getattr(smc_result, "liquidity_levels", []) or []
    bias = getattr(smc_result, "bias", "NEUTRAL")
    if hasattr(bias, "value"):
        bias = bias.value
    swing_high = getattr(smc_result, "swing_high", None)
    swing_low  = getattr(smc_result, "swing_low",  None)
    bos   = getattr(smc_result, "bos_detected",   False)
    choch = getattr(smc_result, "choch_detected",  False)
    premium_zone = discount_zone = None
    in_premium = in_discount = False
    if swing_high is not None and swing_low is not None:
        rng = swing_high - swing_low
        if rng > 0:
            premium_zone  = swing_low + rng * 0.618
            discount_zone = swing_low + rng * 0.382
            if candles:
                cp = candles[-1].get("close", 0)
                in_premium  = cp >= premium_zone
                in_discount = cp <= discount_zone
    liq_sweep    = getattr(smc_result, "liquidity_sweep",   False)
    internal_liq = getattr(smc_result, "internal_liquidity", len(liq) > 2)
    signals_count = len(obs) + len(fvgs) + (1 if bos else 0) + (1 if choch else 0)
    confidence = min(signals_count / 6.0, 1.0)
    htf = getattr(smc_result, "htf_alignment", bias)
    if hasattr(htf, "value"):
        htf = htf.value
    return {
        "smc_analysis": {
            "order_blocks": [_ob_to_dict(ob) for ob in obs],
            "fvgs":         [_fvg_to_dict(f)  for f  in fvgs],
            "bias": bias, "bos": bos, "choch": choch,
        },
        "order_blocks":     [_ob_to_dict(ob)  for ob  in obs],
        "fvgs":             [_fvg_to_dict(f)  for f   in fvgs],
        "liquidity_levels": [_liq_to_dict(l)  for l   in liq],
        "swing_high":       swing_high,
        "swing_low":        swing_low,
        "bias":             bias,
        "premium_zone":     premium_zone,
        "discount_zone":    discount_zone,
        "in_premium_zone":  in_premium,
        "in_discount_zone": in_discount,
        "liquidity_sweep":  liq_sweep,
        "internal_liquidity": internal_liq,
        "bos_detected":    bos,
        "choch_detected":  choch,
        "htf_alignment":   htf,
        "smc_confidence":  round(confidence, 2),
    }


def _extract_ml_context(
    ml_engine: Optional[Any],
    signal_context: Dict[str, Any],
) -> Dict[str, Any]:
    if ml_engine is None:
        return {"ai_prediction": {
            "probability": 0.0, "confidence": 0.0,
            "direction": "NEUTRAL", "model_auc": 0.0,
            "available": False,
        }}
    try:
        features = {
            "confidence":        signal_context.get("confidence", 0.5),
            "rr":                signal_context.get("rr", 0.0),
            "smc_confidence":    signal_context.get("smc_confidence", 0.0),
            "bos_detected":      int(signal_context.get("bos_detected", False)),
            "choch_detected":    int(signal_context.get("choch_detected", False)),
            "in_kill_zone":      int(signal_context.get("in_kill_zone", False)),
            "in_discount_zone":  int(signal_context.get("in_discount_zone", False)),
            "in_premium_zone":   int(signal_context.get("in_premium_zone", False)),
            "liquidity_sweep":   int(signal_context.get("liquidity_sweep", False)),
            "ob_count":          len(signal_context.get("order_blocks", [])),
            "fvg_count":         len(signal_context.get("fvgs", [])),
            "slippage":          signal_context.get("expected_slippage_pips", 2.0),
        }
        result    = ml_engine.predict(features)
        prob      = float(result.get("probability", 0.0))
        direction = "BUY" if prob >= 0.55 else ("SELL" if prob <= 0.45 else "NEUTRAL")
        return {"ai_prediction": {
            "probability":    round(prob, 4),
            "confidence":     round(abs(prob - 0.5) * 2, 4),
            "direction":      direction,
            "model_auc":      float(result.get("model_auc", 0.0)),
            "available":      True,
            "features_used":  list(features.keys()),
        }}
    except Exception as exc:
        logger.warning("[ContextEnricher] ML prediction failed: %s", exc)
        return {"ai_prediction": {
            "probability": 0.0, "confidence": 0.0,
            "direction": "NEUTRAL", "model_auc": 0.0,
            "available": False, "error": str(exc),
        }}


class ContextEnricher:
    """Enriches a signal context dict before it reaches the VotingEngine.

    Usage in SignalProcessor.process():
        enricher = ContextEnricher(smc_engine=smc, ml_engine=ml)
        context  = enricher.enrich(raw_context, candles=candles)
        vote     = voting_engine.vote(agents, context)
    """

    def __init__(
        self,
        smc_engine: Optional[Any] = None,
        ml_engine:  Optional[Any] = None,
    ) -> None:
        self._smc = smc_engine
        self._ml  = ml_engine
        logger.info(
            "[ContextEnricher] init smc=%s ml=%s",
            smc_engine is not None, ml_engine is not None,
        )

    def set_smc_engine(self, engine: Any) -> None:
        self._smc = engine
        logger.info("[ContextEnricher] SMC engine: %s", type(engine).__name__)

    def set_ml_engine(self, engine: Any) -> None:
        self._ml = engine
        logger.info("[ContextEnricher] ML engine: %s", type(engine).__name__)

    def enrich(
        self,
        base_context: Dict[str, Any],
        candles: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Return enriched context. Layers: Session → SMC → ML."""
        ctx    = dict(base_context)
        symbol = ctx.get("symbol", "EURUSD")

        # Layer 1: session
        ctx.update(_get_session_context(symbol))

        # Layer 2: SMC
        smc_result = None
        if self._smc is not None and candles:
            try:
                smc_result = self._smc.analyse(candles)
            except Exception as exc:
                logger.warning("[ContextEnricher] SMCEngine failed: %s", exc)
        ctx.update(_extract_smc_context(smc_result, candles))

        # Layer 3: ML
        ctx.update(_extract_ml_context(self._ml, ctx))

        logger.debug(
            "[ContextEnricher] enriched symbol=%s session=%s bos=%s ml_prob=%.3f",
            symbol, ctx.get("session"), ctx.get("bos_detected"),
            ctx.get("ai_prediction", {}).get("probability", 0.0),
        )
        return ctx


_enricher: Optional[ContextEnricher] = None


def get_context_enricher() -> ContextEnricher:
    global _enricher
    if _enricher is None:
        _enricher = ContextEnricher()
    return _enricher


context_enricher: ContextEnricher = get_context_enricher()
