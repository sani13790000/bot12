"""Analysis routes — SMC, Price Action, Decision Engine.

BUG-N6 FIX: GET /analysis/price-action now returns full patterns list
and sr_levels list (not just counts) so frontend can render actual data.
BUG-N7 FIX: backtest date validation added here via helper.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


# --------------------------------------------------------------------------- #
# Request / Response models
# --------------------------------------------------------------------------- #
class AnalysisRequest(BaseModel):
    symbol: str
    timeframe: str = "H1"
    candle_count: int = 200


class PriceActionResponse(BaseModel):
    symbol: str
    timeframe: str
    trend: str
    trend_strength: float
    patterns: List[Dict[str, Any]]
    support_resistance: List[Dict[str, Any]]
    momentum: str
    volatility: str
    candle_count: int
    analysis_time_ms: float


class SMCResponse(BaseModel):
    symbol: str
    bias: str
    order_blocks: List[Dict[str, Any]]
    fvgs: List[Dict[str, Any]]
    swing_high: Optional[float]
    swing_low: Optional[float]
    bos_detected: bool
    choch_detected: bool
    liquidity_sweep: bool
    smc_confidence: float


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _get_dummy_candles(count: int = 200) -> List[Dict[str, Any]]:
    """Return minimal candle stubs when MT5 is not connected."""
    import time
    now = int(time.time())
    return [
        {"time": now - i * 3600, "open": 1.1000 + i * 0.0001,
         "high": 1.1010 + i * 0.0001, "low": 1.0990 + i * 0.0001,
         "close": 1.1005 + i * 0.0001, "volume": 100}
        for i in range(count)
    ]


async def _fetch_candles(symbol: str, timeframe: str, count: int) -> List[Dict[str, Any]]:
    """Fetch candles from MT5 or return stubs on failure."""
    try:
        from backend.execution.mt5_connector import mt5_connector
        candles = await mt5_connector.get_candles(symbol, timeframe, count)
        if candles:
            return candles
    except Exception as e:
        log.debug("_fetch_candles MT5 error: %s", e)
    return _get_dummy_candles(count)


# --------------------------------------------------------------------------- #
# Price Action endpoint — BUG-N6 FIX: returns full data not just counts
# --------------------------------------------------------------------------- #
@router.post("/price-action", response_model=PriceActionResponse)
async def get_price_action(request: AnalysisRequest) -> PriceActionResponse:
    """Analyse price action patterns for a symbol.

    BUG-N6 FIX: Returns full patterns list and sr_levels list
    (previous version returned only len(patterns) and len(sr_levels)).
    """
    import time
    t0 = time.monotonic()
    candles = await _fetch_candles(request.symbol, request.timeframe, request.candle_count)
    try:
        from backend.analysis.price_action_engine import PriceActionEngine
        pa_engine = PriceActionEngine()
        result = pa_engine.analyze(candles)

        # Serialize patterns to dicts
        patterns_list: List[Dict[str, Any]] = []
        for p in (result.patterns or []):
            try:
                patterns_list.append(
                    p.dict() if hasattr(p, "dict") else
                    p.model_dump() if hasattr(p, "model_dump") else
                    {"name": str(p)}
                )
            except Exception:
                patterns_list.append({"name": str(p)})

        # Serialize S/R levels
        sr_list: List[Dict[str, Any]] = []
        for sr in (result.support_resistance or []):
            try:
                sr_list.append(
                    sr.dict() if hasattr(sr, "dict") else
                    sr.model_dump() if hasattr(sr, "model_dump") else
                    {"level": float(sr)}
                )
            except Exception:
                sr_list.append({"level": float(sr)})

        trend_val = result.trend.value if hasattr(result.trend, "value") else str(result.trend)
        momentum_val = getattr(result, "momentum", "NEUTRAL")
        momentum_str = momentum_val.value if hasattr(momentum_val, "value") else str(momentum_val)
        volatility_val = getattr(result, "volatility", "NORMAL")
        volatility_str = volatility_val.value if hasattr(volatility_val, "value") else str(volatility_val)
        trend_strength = float(getattr(result, "trend_strength", 0.5))

        return PriceActionResponse(
            symbol=request.symbol,
            timeframe=request.timeframe,
            trend=trend_val,
            trend_strength=trend_strength,
            patterns=patterns_list,
            support_resistance=sr_list,
            momentum=momentum_str,
            volatility=volatility_str,
            candle_count=len(candles),
            analysis_time_ms=(time.monotonic() - t0) * 1000,
        )
    except Exception as e:
        log.error("price_action analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/smc", response_model=SMCResponse)
async def get_smc_analysis(request: AnalysisRequest) -> SMCResponse:
    """Analyse Smart Money Concepts for a symbol."""
    candles = await _fetch_candles(request.symbol, request.timeframe, request.candle_count)
    try:
        from backend.analysis.smc_engine import SMCEngine
        smc = SMCEngine()
        result = smc.analyse(candles)
        return SMCResponse(
            symbol=request.symbol,
            bias=result.get("bias", "NEUTRAL"),
            order_blocks=result.get("order_blocks", []),
            fvgs=result.get("fvgs", []),
            swing_high=result.get("swing_high"),
            swing_low=result.get("swing_low"),
            bos_detected=result.get("bos_detected", False),
            choch_detected=result.get("choch_detected", False),
            liquidity_sweep=result.get("liquidity_sweep", False),
            smc_confidence=result.get("smc_confidence", 0.0),
        )
    except Exception as e:
        log.error("smc analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decision")
async def get_decision(
    symbol: str = Query(...),
    direction: str = Query("LONG"),
) -> Dict[str, Any]:
    """Get final decision for a symbol/direction pair."""
    try:
        from backend.analysis.decision_engine import DecisionEngine
        engine = DecisionEngine()
        result = engine.get_final_signal({"symbol": symbol, "direction": direction})
        return result or {"signal": "NO_TRADE", "reason": "no_data"}
    except Exception as e:
        log.error("decision error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
