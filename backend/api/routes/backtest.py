"""Legacy /backtest route — thin wrapper kept for backward compatibility.

The heavy lifting is done by backtest_engine.py (ProcessPool workers).
This router exposes the simpler single-run endpoints that the frontend
original consumed before the engine refactor.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.auth import require_auth
from backend.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class BacktestRequest(BaseModel):
    symbol: str = Field(..., examples=["XAUUSD"])
    timeframe: str = Field("H1", examples=["M15", "H1", "H4", "D1"])
    strategy: str = Field("smc", examples=["smc", "pa", "combined"])
    initial_balance: float = Field(10_000.0, gt=0)
    risk_pct: float = Field(1.0, gt=0, le=10)
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class BacktestResponse(BaseModel):
    status: str
    symbol: str
    timeframe: str
    strategy: str
    total_trades: int
    win_rate: float
    profit_factor: float
    net_pnl: float
    max_drawdown: float
    sharpe_ratio: float
    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/run",
    response_model=BacktestResponse,
    summary="Run a single backtest synchronously (lightweight)",
)
async def run_backtest(
    req: BacktestRequest,
    _user: dict = Depends(require_auth),
) -> Dict[str, Any]:
    """Synchronous backtest — delegates to MultiSymbolBacktestEngine."""
    try:
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        from backend.backtest_engine.data_provider import DataProvider

        provider = DataProvider()
        candles = provider.get_candles(
            symbol=req.symbol,
            timeframe=req.timeframe,  # type: ignore[arg-type]
            start_date=req.start_date,
            end_date=req.end_date,
        )
        engine = MultiSymbolBacktestEngine(
            symbol=req.symbol,
            timeframe=req.timeframe,  # type: ignore[arg-type]
            initial_balance=req.initial_balance,
            risk_pct=req.risk_pct,
        )
        result: Dict[str, Any] = engine.run(
            candles=candles,
            strategy=req.strategy,
        )
        return {
            "status": "completed",
            "symbol": req.symbol,
            "timeframe": req.timeframe,
            "strategy": req.strategy,
            "total_trades": result.get("total_trades", 0),
            "win_rate": result.get("win_rate", 0.0),
            "profit_factor": result.get("profit_factor", 0.0),
            "net_pnl": result.get("net_pnl", 0.0),
            "max_drawdown": result.get("max_drawdown", 0.0),
            "sharpe_ratio": result.get("sharpe_ratio", 0.0),
            "trades": result.get("trades", []),
            "equity_curve": result.get("equity_curve", []),
        }
    except Exception as exc:
        logger.error("Backtest failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backtest failed: {exc}",
        ) from exc


@router.get("/symbols", summary="List supported symbols")
async def list_symbols(_user: dict = Depends(require_auth)) -> Dict[str, Any]:
    """Return the list of symbols the backtest engine supports."""
    return {
        "symbols": [
            "XAUUSD", "EURUSD", "GBPUSD", "USDJPY",
            "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
            "BTCUSD", "ETHUSD", "US30", "NAS100",
            "UKOIL", "USOIL",
        ],
        "timeframes": ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1"],
        "strategies": ["smc", "pa", "combined", "rl"],
    }
