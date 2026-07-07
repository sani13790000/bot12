"""Analysis routes — SMC + Price Action.
BUG-AF2 FIX: removed prefix="/analysis" -- double prefix was causing /analysis/analysis/*
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, validator

from backend.core.deps import get_current_user

log    = logging.getLogger(__name__)
router = APIRouter(tags=["analysis"])


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
    def validate_candle_count(cls, v):
        from backend.core.config import get_settings
        max_c = get_settings().SMC_MAX_CANDLES
        if len(v) > max_c: raise ValueError(f"Too many candles: {len(v)} > {max_c}")
        if len(v) < 2: raise ValueError("At least 2 candles required.")
        return v


class PAAnalysisRequest(BaseModel):
    symbol:    str
    candles:   List[CandleData]
    timeframe: str = "H1"

    @validator("candles")
    def validate_candle_count(cls, v):
        from backend.core.config import get_settings
        max_c = get_settings().SMC_MAX_CANDLES
        if len(v) > max_c: raise ValueError(f"Too many candles: {len(v)} > {max_c}")
        if len(v) < 2: raise ValueError("At least 2 candles required.")
        return v


@router.post("/smc")
async def analyze_smc(request: SMCAnalysisRequest, _user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        from backend.analysis.smc_engine import SMCEngine
        engine = SMCEngine()
        candles = [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in request.candles]
        result = engine.analyse(candles)
        return {"symbol": request.symbol, "timeframe": request.timeframe, "candle_count": len(candles), "analysis": result}
    except ValueError: raise
    except Exception as e: log.error("SMC analysis error: %s", e); raise HTTPException(status_code=500, detail=str(e))


@router.post("/price-action")
async def analyze_price_action(request: PAAnalysisRequest, _user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        from backend.analysis.price_action_engine import PriceActionEngine
        engine = PriceActionEngine()
        candles = [{"open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in request.candles]
        result = engine.analyze(candles)
        sr_levels = [{"price": lvl.price, "type": str(lvl.level_type), "strength": getattr(lvl, "strength", 0.0)} for lvl in getattr(result, "support_resistance", [])]
        patterns = [{"name": getattr(p, "name", str(p)), "direction": getattr(p, "direction", None), "confidence": getattr(p, "confidence", 0.0)} for p in getattr(result, "patterns", [])]
        return {"symbol": request.symbol, "timeframe": request.timeframe, "candle_count": len(candles), "trend": str(getattr(result, "trend", "")), "patterns": patterns, "patterns_count": len(patterns), "sr_levels": sr_levels, "sr_count": len(sr_levels), "momentum": getattr(result, "momentum", None), "volatility": getattr(result, "volatility", None)}
    except ValueError: raise
    except Exception as e: log.error("PA analysis error: %s", e); raise HTTPException(status_code=500, detail=str(e))
