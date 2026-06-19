"""Backtest Engine Routes — Galaxy Vast AI Trading Platform

Fix applied:
  - ThreadPoolExecutor replaced with asyncio.run_in_executor
    to avoid blocking the FastAPI async event loop.
  - Race condition in _latest dict fixed with asyncio.Lock
"""
from __future__ import annotations

import asyncio
import functools
from concurrent.futures import ProcessPoolExecutor
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.logger import get_logger

logger = get_logger("api.backtest_engine")
router = APIRouter()

# ProcessPoolExecutor for CPU-bound backtest work (not ThreadPoolExecutor)
_executor = ProcessPoolExecutor(max_workers=4)

# Thread-safe results store
_latest: Dict[str, Any] = {}
_lock = asyncio.Lock()


# ── Models ──
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


class OptimizeRequest(BaseModel):
    symbol: str = Field(default="XAUUSD")
    timeframe: str = Field(default="M15")
    param_grid: Dict[str, Any] = Field(default_factory=dict)
    initial_balance: float = Field(default=10000.0, ge=100)
    metric: str = Field(default="sharpe")


# ── CPU-bound worker functions (run in ProcessPool) ──
def _run_backtest_sync(req_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous backtest — runs in separate process to avoid GIL."""
    try:
        from backend.institutional.tick_backtest import TickBacktestEngine
        engine = TickBacktestEngine(
            symbol=req_dict["symbol"],
            initial_balance=req_dict["initial_balance"],
            spread_pips=req_dict["spread_pips"],
            slippage_pips=req_dict["slippage_pips"],
            commission_per_lot=req_dict["commission_per_lot"],
        )
        return engine.run()
    except Exception as exc:
        return {"error": str(exc)}


def _run_wfo_sync(req_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Synchronous walk-forward — runs in separate process."""
    try:
        from backend.institutional.walk_forward_optimizer import WalkForwardOptimizer
        optimizer = WalkForwardOptimizer(
            symbol=req_dict["symbol"],
            timeframe=req_dict["timeframe"],
            n_splits=req_dict["is_periods"],
            oos_ratio=req_dict["oos_ratio"],
        )
        return optimizer.run()
    except Exception as exc:
        return {"error": str(exc)}


# ── Async wrappers using run_in_executor (non-blocking) ──
async def _run_backtest_async(req_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Run CPU-bound backtest without blocking event loop."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        _executor,
        functools.partial(_run_backtest_sync, req_dict)
    )
    async with _lock:
        _latest[req_dict["symbol"]] = result
    return result


async def _run_wfo_async(req_dict: Dict[str, Any]) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        functools.partial(_run_wfo_sync, req_dict)
    )


# ── Endpoints ──
@router.post("/run", tags=["Backtest Engine"])
async def run_backtest(req: BacktestEngineRequest):
    """Run tick-level backtest (non-blocking)."""
    try:
        result = await _run_backtest_async(req.model_dump())
        return {"status": "completed", "symbol": req.symbol, "result": result}
    except Exception as exc:
        logger.error("Backtest failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {exc}"
        )


@router.post("/wfo", tags=["Backtest Engine"])
async def run_wfo(req: WFORequest):
    """Run Walk-Forward Optimization (non-blocking)."""
    try:
        result = await _run_wfo_async(req.model_dump())
        return {"status": "completed", "symbol": req.symbol, "result": result}
    except Exception as exc:
        logger.error("WFO failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"WFO failed: {exc}"
        )


@router.get("/latest/{symbol}", tags=["Backtest Engine"])
async def get_latest_result(symbol: str):
    """Get latest backtest result for a symbol (thread-safe)."""
    async with _lock:
        result = _latest.get(symbol.upper())
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No backtest results found for {symbol}"
        )
    return result


@router.get("/health", tags=["Backtest Engine"])
async def backtest_engine_health():
    return {
        "status": "healthy",
        "executor": "ProcessPoolExecutor",
        "max_workers": 4,
        "cached_symbols": list(_latest.keys()),
    }
