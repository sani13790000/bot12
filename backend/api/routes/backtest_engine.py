"""Backtest Engine Routes — Galaxy Vast AI
Fix: ProcessPoolExecutor + asyncio.run_in_executor (non-blocking)
Fix: asyncio.Lock for thread-safe _latest dict
"""
from __future__ import annotations
import asyncio, functools
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from backend.core.logger import get_logger

logger = get_logger("api.backtest_engine")
router = APIRouter()
_executor = ProcessPoolExecutor(max_workers=4)
_latest: Dict[str, Any] = {}
_lock = asyncio.Lock()


class BacktestEngineRequest(BaseModel):
    symbol: str = Field(default="XAUUSD")
    timeframe: str = Field(default="M15")
    start_date: str = Field(default="2024-01-01")
    end_date: str = Field(default="2024-12-31")
    initial_balance: float = Field(default=10000.0, ge=100)
    risk_per_trade: float = Field(default=1.0, ge=0.1, le=10.0)
    spread_pips: float = Field(default=2.0, ge=0)
    slippage_pips: float = Field(default=0.5, ge=0)
    commission_per_lot: float = Field(default=7.0, ge=0)
    n_simulations: int = Field(default=1000, ge=100, le=10000)
    strategy: str = Field(default="smc")


class WFORequest(BaseModel):
    symbol: str = Field(default="XAUUSD")
    timeframe: str = Field(default="M15")
    is_periods: int = Field(default=3, ge=2, le=20)
    oos_ratio: float = Field(default=0.3, ge=0.1, le=0.5)
    initial_balance: float = Field(default=10000.0, ge=100)


def _run_bt(d: Dict) -> Dict:
    try:
        from backend.institutional.tick_backtest import TickBacktestEngine
        return TickBacktestEngine(
            symbol=d["symbol"],
            initial_balance=d["initial_balance"],
            spread_pips=d["spread_pips"],
            slippage_pips=d["slippage_pips"],
            commission_per_lot=d["commission_per_lot"],
        ).run()
    except Exception as e:
        return {"error": str(e)}


def _run_wfo(d: Dict) -> Dict:
    try:
        from backend.institutional.walk_forward_optimizer import WalkForwardOptimizer
        return WalkForwardOptimizer(
            symbol=d["symbol"], timeframe=d["timeframe"],
            n_splits=d["is_periods"], oos_ratio=d["oos_ratio"],
        ).run()
    except Exception as e:
        return {"error": str(e)}


@router.post("/run")
async def run_backtest(req: BacktestEngineRequest):
    """Run tick-level backtest — non-blocking via ProcessPoolExecutor."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, functools.partial(_run_bt, req.model_dump()))
        async with _lock:
            _latest[req.symbol.upper()] = result
        return {"status": "completed", "symbol": req.symbol, "result": result}
    except Exception as exc:
        logger.error("Backtest failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")


@router.post("/wfo")
async def run_wfo(req: WFORequest):
    """Run Walk-Forward Optimization — non-blocking."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(_executor, functools.partial(_run_wfo, req.model_dump()))
        return {"status": "completed", "symbol": req.symbol, "result": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"WFO failed: {exc}")


@router.get("/latest/{symbol}")
async def get_latest(symbol: str):
    async with _lock:
        result = _latest.get(symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"No results for {symbol}")
    return result


@router.get("/health")
async def health():
    return {"status": "healthy", "executor": "ProcessPoolExecutor", "max_workers": 4}
