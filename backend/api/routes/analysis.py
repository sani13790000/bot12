"""Analysis routes — SMC + Price Action.

BUG-P4 FIX: candle count validation — max settings.SMC_MAX_CANDLES (default 1000)
Old: no limit — 100K candles possible — memory spike
New: validator rejects oversized payloads with 422 before any processing
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])


class CandleData(BaseModel):
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float         = 0.0
    time:   Optional[int] = None


class SMCAnalysisRequest(BaseModel):
    symbol:    str
    candles:   List[CandleData]
    timeframe: str = "H1"

    @validator("candles")
    def validate_candle_count(cls, v: List[CandleData]) -> List[CandleData]:
        """BUG-P4 FIX: reject oversized payloads early."""
        from backend.core.config import get_settings
        max_c = get_settings().SMC_MAX_CANDLES
        if len(v) > max_c:
            raise ValueError(f"Too many candles: {len(v)} > max {max_c}. Reduce or raise SMC_MAX_CANDLES.")
        if len(v) < 2:
            raise ValueError("At least 2 candles required.")
        return v


class PAAnalysisRequest(BaseModel):
    symbol:    str
    candles:   List[CandleData]
    timeframe: str = "H1"

    @validator("candles")
    def validate_candle_count(cls, v: List[CandleData]) -> List[CandleData]:
        from backend.core.config import get_settings
        max_c = get_settings().SMC_MAX_CANDLES
        if len(v) > max_c:
            raise ValueError(f"Too many candles: {len(v)} > max {max_c}.")
        if len(v) < 2:
            raise ValueError("At least 2 candles required.")
        return v


@router.post("/smc")
async def analyze_smc(request: SMCAnalysisRequest) -> Dict[str, Any]:
    """Full SMC analysis."""
    try:
        from backend.analysis.smc_engine import SMCEngine
        engine  = SMCEngine()
        candles = [{"open": c.open, "high": c.high, "low": c.low,
                    "close": c.close, "volume": c.volume} for c in request.candles]
        result  = engine.analyse(candles)
        return {"symbol": request.symbol, "timeframe": request.timeframe,
                "candle_count": len(candles), "analysis": result}
    except ValueError:
        raise
    except Exception as e:
        log.error("SMC analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-action")
async def analyze_price_action(request: PAAnalysisRequest) -> Dict[str, Any]:
    """Full PA analysis — returns complete result (patterns list, SR levels list).

    Previous bug: returned only counts. Now returns full lists for frontend.
    """
    try:
        from backend.analysis.price_action_engine import PriceActionEngine
        engine  = PriceActionEngine()
        candles = [{"open": c.open, "high": c.high, "low": c.low,
                    "close": c.close, "volume": c.volume} for c in request.candles]
        result  = engine.analyze(candles)

        sr_levels = []
        if hasattr(result, "support_resistance") and result.support_resistance:
            sr_levels = [
                {"price": lvl.price,
                 "type":  lvl.level_type.value if hasattr(lvl.level_type, "value") else str(lvl.level_type),
                 "strength": getattr(lvl, "strength", 0.0)}
                for lvl in result.support_resistance
            ]

        patterns = []
        if hasattr(result, "patterns") and result.patterns:
            patterns = [
                {"name":       p.name if hasattr(p, "name") else str(p),
                 "direction":  getattr(p, "direction", None),
                 "confidence": getattr(p, "confidence", 0.0)}
                for p in result.patterns
            ]

        return {
            "symbol":         request.symbol,
            "timeframe":      request.timeframe,
            "candle_count":   len(candles),
            "trend":          result.trend.value if hasattr(result.trend, "value") else str(result.trend),
            "patterns":       patterns,
            "patterns_count": len(patterns),
            "sr_levels":      sr_levels,
            "sr_count":       len(sr_levels),
            "momentum":       getattr(result, "momentum", None),
            "volatility":     getattr(result, "volatility", None),
        }
    except ValueError:
        raise
    except Exception as e:
        log.error("PA analysis error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
