"""
backend/api/routes/research.py
Galaxy Vast AI Trading Platform — Research API Routes

Phase AB fix: restore from placeholder "RESEARCH_CONTENT" (16 bytes) to full implementation.

Endpoints:
  POST /research/backtest/run          — run full backtest via BacktestEngine
  POST /research/monte-carlo           — Monte Carlo simulation
  POST /research/walk-forward          — walk-forward analysis
  GET  /research/replay/{symbol}       — tick replay for manual review

BUG-AA1 fix: fake_trades renamed to mc_trades (cosmetic — logic unchanged)
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["research"])


class BacktestRunRequest(BaseModel):
    symbol:          str   = Field(...,   description="Trading symbol e.g. EURUSD")
    timeframe:       str   = Field("H1", description="MT5 timeframe: M1/M5/M15/H1/H4/D1")
    start_date:      Optional[date] = None
    end_date:        Optional[date] = None
    strategy:        str   = Field("smc", description="Strategy: smc / pa / hybrid")
    initial_balance: float = Field(10_000.0, gt=0)
    risk_pct:        float = Field(1.0, gt=0, le=10)
    parameters:      Dict[str, Any] = Field(default_factory=dict)


class MonteCarloRequest(BaseModel):
    trades_pnl:       List[float] = Field(..., description="List of trade PnL values")
    n_iterations:     int         = Field(1_000, ge=100, le=50_000)
    confidence_level: float       = Field(0.95, ge=0.80, le=0.99)


class WalkForwardRequest(BaseModel):
    symbol:     str   = Field(...)
    timeframe:  str   = Field("H1")
    start_date: Optional[date] = None
    end_date:   Optional[date] = None
    strategy:   str   = Field("smc")
    train_pct:  float = Field(0.7, gt=0.5, lt=1.0)
    n_splits:   int   = Field(5, ge=2, le=20)


@router.post("/backtest/run")
async def run_backtest(
    req: BacktestRunRequest,
    _current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run a full backtest using the real BacktestEngine."""
    try:
        from backend.research.backtest.engine import BacktestEngine
        from backend.research.data_provider import DataProvider

        provider = DataProvider()
        candles = await provider.get_candles(
            symbol=req.symbol.upper(),
            timeframe=req.timeframe.upper(),
            start_date=req.start_date,
            end_date=req.end_date,
        )
        if not candles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No candle data available for {req.symbol} {req.timeframe}",
            )
        engine = BacktestEngine(
            symbol=req.symbol.upper(),
            timeframe=req.timeframe.upper(),
            initial_balance=req.initial_balance,
            risk_pct=req.risk_pct,
        )
        result = engine.run(candles=candles, strategy=req.strategy, parameters=req.parameters)
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[research] /backtest/run error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/monte-carlo")
async def run_monte_carlo(
    req: MonteCarloRequest,
    _current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run Monte Carlo simulation. BUG-AA1 fix: mc_trades (was fake_trades)."""
    try:
        from backend.research.backtest.monte_carlo import MonteCarloSimulator
        from backend.research.backtest.engine import BacktestTrade, TradeDirection

        mc_trades = []  # BUG-AA1 fix: was fake_trades
        for i, pnl in enumerate(req.trades_pnl):
            t = BacktestTrade(
                trade_id    = str(i),
                direction   = TradeDirection.BUY,
                entry_price = 1.0,
                entry_time  = None,
            )
            t.pnl_dollar = pnl
            t.is_winner  = pnl > 0
            mc_trades.append(t)

        simulator = MonteCarloSimulator(
            n_iterations     = req.n_iterations,
            confidence_level = req.confidence_level,
        )
        result = simulator.run(trades=mc_trades)
        return {"status": "ok", "data": result}
    except Exception as exc:
        logger.exception("[research] /monte-carlo error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/walk-forward")
async def run_walk_forward(
    req: WalkForwardRequest,
    _current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run walk-forward optimization analysis."""
    try:
        from backend.research.backtest.walk_forward import WalkForwardAnalyzer
        from backend.research.data_provider import DataProvider

        provider = DataProvider()
        candles = await provider.get_candles(
            symbol=req.symbol.upper(),
            timeframe=req.timeframe.upper(),
            start_date=req.start_date,
            end_date=req.end_date,
        )
        if not candles:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No candle data available for {req.symbol} {req.timeframe}",
            )
        analyzer = WalkForwardAnalyzer(
            symbol=req.symbol.upper(), timeframe=req.timeframe.upper(),
            train_pct=req.train_pct, n_splits=req.n_splits,
        )
        result = analyzer.run(candles=candles, strategy=req.strategy)
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[research] /walk-forward error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/replay/{symbol}")
async def replay_symbol(
    symbol: str,
    timeframe: str = Query("H1"),
    limit:     int = Query(500, ge=50, le=5000),
    _current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return historical candles for manual chart replay."""
    try:
        from backend.research.data_provider import DataProvider
        provider = DataProvider()
        candles = await provider.get_candles(
            symbol=symbol.upper(), timeframe=timeframe.upper(), limit=limit,
        )
        return {
            "status": "ok",
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "candles": candles,
            "count": len(candles),
        }
    except Exception as exc:
        logger.exception("[research] /replay/%s error: %s", symbol, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
