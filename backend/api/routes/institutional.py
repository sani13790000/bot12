"""Institutional API routes.
BUG-AF6 FIX: removed prefix="/institutional" -- double prefix was causing /institutional/institutional/*
Now: prefix provided by main.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["institutional"])


class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    initial_balance: float = 10_000.0
    risk_pct: float = 1.0
    spread_multiplier: float = 1.0
    slippage_pips: float = 0.5
    use_commission: bool = True
    candles: List[Dict[str, Any]] = Field(default_factory=list)


class MonteCarloRequest(BaseModel):
    trade_pnls: List[float]
    initial_balance: float = 10_000.0
    n_simulations: int = 1000
    ruin_threshold_pct: float = 50.0
    seed: Optional[int] = 42


@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest):
    try:
        from backend.institutional.tick_backtest import TickBacktestConfig, TickBacktestEngine

        config = TickBacktestConfig(
            symbol=req.symbol,
            timeframe=req.timeframe,
            initial_balance=req.initial_balance,
            risk_pct_per_trade=req.risk_pct,
            spread_multiplier=req.spread_multiplier,
            slippage_pips=req.slippage_pips,
            use_commission=req.use_commission,
        )
        engine = TickBacktestEngine(config)
        if not req.candles:
            return {"message": "No candles provided.", "status": "empty"}

        def signal_fn(candle, history):
            if len(history) < 50:
                return None
            closes = [c["close"] for c in history]
            ema20 = sum(closes[-20:]) / 20
            ema50 = sum(closes[-50:]) / 50
            if ema20 > ema50 * 1.001:
                return {
                    "direction": "BUY",
                    "stop_loss": candle["close"] - candle.get("atr", 10),
                    "take_profit": candle["close"] + candle.get("atr", 10) * 2,
                }
            elif ema20 < ema50 * 0.999:
                return {
                    "direction": "SELL",
                    "stop_loss": candle["close"] + candle.get("atr", 10),
                    "take_profit": candle["close"] - candle.get("atr", 10) * 2,
                }
            return None

        result = engine.run(req.candles, signal_fn)
        return {
            "total_trades": result.total_trades,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "sharpe_ratio": result.sharpe_ratio,
            "final_balance": result.final_balance,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monte-carlo/run")
async def run_monte_carlo(req: MonteCarloRequest):
    try:
        from backend.institutional.monte_carlo import MonteCarloSimulator

        sim = MonteCarloSimulator(req.n_simulations, req.ruin_threshold_pct, req.seed)
        result = sim.run(req.trade_pnls, req.initial_balance)
        return {
            "n_simulations": result.n_simulations,
            "probability_of_ruin": result.probability_of_ruin,
            "median_final_balance": result.median_final_balance,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def institutional_health():
    modules = {}
    for name, mod_path, cls in [
        ("market_replay", "backend.institutional.market_replay", "MarketReplayEngine"),
        ("tick_backtest", "backend.institutional.tick_backtest", "TickBacktestEngine"),
        ("monte_carlo", "backend.institutional.monte_carlo", "MonteCarloSimulator"),
    ]:
        try:
            import importlib

            m = importlib.import_module(mod_path)
            getattr(m, cls)
            modules[name] = "ok"
        except Exception as e:
            modules[name] = f"error: {str(e)[:60]}"
    all_ok = all(v == "ok" for v in modules.values())
    return {"status": "healthy" if all_ok else "degraded", "modules": modules}
