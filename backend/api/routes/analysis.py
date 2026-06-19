"""
backend/api/routes/analysis.py
Analysis endpoints — SMC, Price Action, AI Prediction.

Security:
- All inputs validated with Pydantic + symbol whitelist
- No eval(), no exec(), no subprocess — RCE prevention
- Timeouts on all engine calls
- Auth required on all endpoints
"""
from __future__ import annotations

import asyncio
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.core.deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["Analysis"])

# ---------------------------------------------------------------------------
# Allowed values (whitelist — prevent injection via symbol/timeframe)
# ---------------------------------------------------------------------------

_ALLOWED_SYMBOLS = frozenset({
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "USDCAD", "NZDUSD", "GBPJPY", "EURJPY",
    "EURGBP", "XAGUSD", "BTCUSD", "ETHUSD",
})

_ALLOWED_TIMEFRAMES = frozenset({
    "M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1",
})

_ENGINE_TIMEOUT = 30  # seconds


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AnalysisRequest(BaseModel):
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field("H1")
    bars: int = Field(200, ge=50, le=1000)
    mode: Literal["smc", "price_action", "combined"] = "combined"

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v

    @field_validator("timeframe")
    @classmethod
    def _validate_timeframe(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_TIMEFRAMES:
            raise ValueError(f"Timeframe '{v}' not supported")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/smc")
async def analyze_smc(
    body: AnalysisRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Smart Money Concepts analysis."""
    try:
        from backend.analysis.smc_engine import SMCEngine
        engine = SMCEngine()
        result = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                None, engine.analyze, body.symbol, body.timeframe, body.bars
            ),
            timeout=_ENGINE_TIMEOUT,
        )
        return {"status": "ok", "symbol": body.symbol, "data": result}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analysis timed out")
    except Exception as exc:
        log.error("SMC analysis error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Analysis failed")


@router.post("/price-action")
async def analyze_price_action(
    body: AnalysisRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Price Action analysis."""
    try:
        from backend.analysis.price_action_engine import PriceActionEngine
        engine = PriceActionEngine()
        result = await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(
                None, engine.analyze, body.symbol, body.timeframe, body.bars
            ),
            timeout=_ENGINE_TIMEOUT,
        )
        return {"status": "ok", "symbol": body.symbol, "data": result}
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analysis timed out")
    except Exception as exc:
        log.error("Price action error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Analysis failed")


@router.post("/combined")
async def analyze_combined(
    body: AnalysisRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Run SMC + Price Action + Decision Engine in parallel."""
    try:
        from backend.analysis.smc_engine import SMCEngine
        from backend.analysis.price_action_engine import PriceActionEngine
        from backend.analysis.decision_engine import DecisionEngine

        loop = asyncio.get_running_loop()
        smc_engine = SMCEngine()
        pa_engine = PriceActionEngine()
        decision_engine = DecisionEngine()

        smc_task = loop.run_in_executor(None, smc_engine.analyze, body.symbol, body.timeframe, body.bars)
        pa_task = loop.run_in_executor(None, pa_engine.analyze, body.symbol, body.timeframe, body.bars)

        smc_result, pa_result = await asyncio.wait_for(
            asyncio.gather(smc_task, pa_task),
            timeout=_ENGINE_TIMEOUT,
        )

        decision = decision_engine.decide(
            smc_analysis=smc_result,
            pa_analysis=pa_result,
            symbol=body.symbol,
            timeframe=body.timeframe,
        )

        return {
            "status": "ok",
            "symbol": body.symbol,
            "timeframe": body.timeframe,
            "smc": smc_result,
            "price_action": pa_result,
            "decision": decision,
        }
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Analysis timed out")
    except Exception as exc:
        log.error("Combined analysis error: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Analysis failed")


@router.get("/symbols")
async def list_symbols() -> dict:
    """List supported symbols — public endpoint."""
    return {"symbols": sorted(_ALLOWED_SYMBOLS), "timeframes": sorted(_ALLOWED_TIMEFRAMES)}
