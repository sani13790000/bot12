"""Backtest routes.

BUG-N7 FIX: date_range validation added — start_date must be before end_date.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, validator

log = logging.getLogger(__name__)
router = APIRouter(prefix="/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str
    start_date: str  # ISO format e.g. "2025-01-01"
    end_date: str    # ISO format e.g. "2025-12-31"
    strategy: str = "smc_default"
    initial_balance: float = 10_000.0
    risk_per_trade_pct: float = 1.0
    max_workers: int = 2

    @validator("end_date")
    def end_after_start(cls, end_date: str, values: Dict[str, Any]) -> str:
        """BUG-N7 FIX: validate start_date < end_date."""
        start = values.get("start_date")
        if start:
            try:
                dt_start = datetime.fromisoformat(start)
                dt_end = datetime.fromisoformat(end_date)
                if dt_end <= dt_start:
                    raise ValueError(
                        f"end_date ({end_date}) must be after start_date ({start})"
                    )
            except ValueError as e:
                if "must be after" in str(e):
                    raise
                raise ValueError(f"Invalid date format: {e}") from e
        return end_date


class BacktestResult(BaseModel):
    symbol: str
    strategy: str
    start_date: str
    end_date: str
    total_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    status: str
    duration_seconds: float
    details: Dict[str, Any]


@router.post("/run", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest) -> BacktestResult:
    """Run a backtest for the given symbol and date range."""
    import time
    t0 = time.monotonic()
    try:
        from backend.services.backtest_engine import BacktestEngine
        engine = BacktestEngine(
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            strategy=request.strategy,
            initial_balance=request.initial_balance,
            risk_per_trade_pct=request.risk_per_trade_pct,
            max_workers=min(request.max_workers, 4),
        )
        result = await engine.run(timeout=300)
        duration = time.monotonic() - t0
        return BacktestResult(
            symbol=request.symbol,
            strategy=request.strategy,
            start_date=request.start_date,
            end_date=request.end_date,
            total_trades=result.get("total_trades", 0),
            win_rate=result.get("win_rate", 0.0),
            total_pnl=result.get("total_pnl", 0.0),
            max_drawdown=result.get("max_drawdown", 0.0),
            sharpe_ratio=result.get("sharpe_ratio", 0.0),
            status="completed",
            duration_seconds=round(duration, 2),
            details=result,
        )
    except Exception as e:
        log.error("backtest error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_backtest_history(limit: int = 20) -> Dict[str, Any]:
    """Get recent backtest results from DB."""
    try:
        from backend.database.connection import get_db_client
        import asyncio
        db = await get_db_client()
        r = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: db.table("backtest_results")
                .select("*").order("created_at", desc=True).limit(limit).execute()
            ),
            timeout=10.0,
        )
        return {"results": r.data or [], "count": len(r.data or [])}
    except Exception as e:
        log.debug("backtest history: %s", e)
        return {"results": [], "count": 0, "note": str(e)}
