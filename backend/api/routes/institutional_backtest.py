"""
Galaxy Vast AI Trading Platform
Institutional Backtest API Routes — v3.0.0

Endpoints:
  POST /api/v1/institutional-backtest/run           — Multi-symbol backtest
  POST /api/v1/institutional-backtest/optimize      — Parameter optimization
  POST /api/v1/institutional-backtest/walk-forward  — Walk-forward analysis
  POST /api/v1/institutional-backtest/monte-carlo   — Monte Carlo simulation
  GET  /api/v1/institutional-backtest/report/html   — HTML performance report
  GET  /api/v1/institutional-backtest/report/json   — JSON performance report
  GET  /api/v1/institutional-backtest/risk-report   — HTML risk report
  GET  /api/v1/institutional-backtest/status        — Engine status
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from backend.backtest_engine.multi_symbol_engine import (
    MultiSymbolBacktestEngine,
    MultiSymbolConfig,
    MultiSymbolResult,
    Timeframe,
)
from backend.backtest_engine.parameter_optimizer import (
    ParameterOptimizer,
    OptimizationConfig,
    ParameterRange,
)
from backend.backtest_engine.walk_forward_advanced import (
    WalkForwardAdvancedEngine,
    WalkForwardAdvancedConfig,
)
from backend.backtest_engine.monte_carlo_advanced import (
    MonteCarloAdvancedSimulator,
    MonteCarloAdvancedConfig,
)
from backend.backtest_engine.performance_report import PerformanceReportGenerator
from backend.backtest_engine.risk_report import RiskReportGenerator
from backend.backtest_engine.data_provider import CandleDataProvider, CandleBar

router = APIRouter(prefix="/api/v1/institutional-backtest", tags=["Institutional Backtest"])

# ── Singletons ────────────────────────────────────────────────────────────────
_provider    = CandleDataProvider()
_engine      = MultiSymbolBacktestEngine(_provider)
_optimizer   = ParameterOptimizer(_provider)
_wf_engine   = WalkForwardAdvancedEngine(_provider)
_mc_sim      = MonteCarloAdvancedSimulator()
_perf_report = PerformanceReportGenerator()
_risk_report = RiskReportGenerator()

# Cache last results for report generation
_last_backtest_result:  Optional[MultiSymbolResult] = None
_last_mc_result         = None


# ── Request Models ────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbols:            List[str]            = Field(["XAUUSD", "EURUSD"])
    primary_timeframe:  str                  = Field("H1")
    initial_balance:    float                = Field(10_000.0, ge=100)
    risk_per_trade_pct: float                = Field(1.0, ge=0.1, le=5.0)
    rr_ratio:           float                = Field(2.0, ge=1.0, le=10.0)
    min_confidence:     float                = Field(65.0, ge=0, le=100)
    n_candles:          int                  = Field(1500, ge=200, le=10000)
    start_price:        float                = Field(2000.0)
    use_atr_sizing:     bool                 = Field(True)
    atr_multiplier:     float                = Field(1.5, ge=0.5, le=5.0)
    commission_per_lot: float                = Field(7.0, ge=0)


class ParameterRangeRequest(BaseModel):
    name:   str
    values: List[Any]


class OptimizeRequest(BaseModel):
    symbols:            List[str]            = Field(["XAUUSD"])
    method:             str                  = Field("GRID")
    optimization_metric:str                 = Field("SHARPE")
    initial_balance:    float                = Field(10_000.0)
    parameter_ranges:   List[ParameterRangeRequest] = Field(default_factory=list)
    n_candles:          int                  = Field(1000)


class WalkForwardRequest(BaseModel):
    symbols:       List[str]  = Field(["XAUUSD"])
    is_months:     int        = Field(6, ge=1, le=24)
    oos_months:    int        = Field(2, ge=1, le=12)
    step_months:   int        = Field(1, ge=1, le=6)
    mode:          str        = Field("ROLLING")
    initial_balance: float    = Field(10_000.0)
    n_candles:     int        = Field(2000)
    optimization_metric: str = Field("SHARPE")


class MonteCarloRequest(BaseModel):
    n_simulations:      int   = Field(1000, ge=100, le=10000)
    initial_balance:    float = Field(10_000.0)
    ruin_threshold_pct: float = Field(20.0, ge=5, le=50)
    seed:               Optional[int] = None
    resampling_method:  str   = Field("SHUFFLE")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_data(symbols: List[str], n_candles: int, start_price: float = 2000.0) -> None:
    for sym in symbols:
        if not _provider.has(sym, Timeframe.H1):
            _provider.generate_synthetic(
                sym, Timeframe.H1,
                n_candles=n_candles,
                start_price=start_price if "XAU" in sym else 1.1,
            )


def _parse_timeframe(tf: str) -> Timeframe:
    mapping = {"M1": Timeframe.M1, "M5": Timeframe.M5, "M15": Timeframe.M15,
               "H1": Timeframe.H1, "H4": Timeframe.H4, "D1": Timeframe.D1}
    return mapping.get(tf.upper(), Timeframe.H1)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """Run institutional multi-symbol, multi-timeframe backtest."""
    global _last_backtest_result

    _ensure_data(req.symbols, req.n_candles, req.start_price)

    config = MultiSymbolConfig(
        symbols=req.symbols,
        primary_timeframe=_parse_timeframe(req.primary_timeframe),
        initial_balance=req.initial_balance,
        risk_per_trade_pct=req.risk_per_trade_pct,
        rr_ratio=req.rr_ratio,
        min_confidence=req.min_confidence,
        use_atr_sizing=req.use_atr_sizing,
        atr_multiplier=req.atr_multiplier,
        commission_per_lot=req.commission_per_lot,
    )

    try:
        result = await _engine.run(config)
        _last_backtest_result = result
        return JSONResponse(content={"success": True, "data": result.to_dict()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/optimize")
async def run_optimization(req: OptimizeRequest):
    """Run parameter optimization (Grid or Genetic)."""
    _ensure_data(req.symbols, req.n_candles)

    param_ranges = [
        ParameterRange(name=pr.name, values=pr.values)
        for pr in req.parameter_ranges
    ] if req.parameter_ranges else [
        ParameterRange("rr_ratio",           [1.5, 2.0, 2.5]),
        ParameterRange("min_confidence",     [60.0, 65.0, 70.0]),
        ParameterRange("atr_multiplier",     [1.0, 1.5, 2.0]),
        ParameterRange("risk_per_trade_pct", [0.5, 1.0]),
    ]

    opt_config = OptimizationConfig(
        symbols=req.symbols,
        parameter_ranges=param_ranges,
        method=req.method.upper(),
        optimization_metric=req.optimization_metric.upper(),
        initial_balance=req.initial_balance,
    )

    try:
        result = await _optimizer.optimize(opt_config)
        return JSONResponse(content={"success": True, "data": result.to_dict()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/walk-forward")
async def run_walk_forward(req: WalkForwardRequest):
    """Run advanced walk-forward analysis with per-window optimization."""
    _ensure_data(req.symbols, req.n_candles)

    dataset = _provider.get(req.symbols[0], Timeframe.H1)
    if not dataset or not dataset.candles:
        raise HTTPException(status_code=400, detail="No data available")

    start = dataset.candles[0].time
    end   = dataset.candles[-1].time

    wf_config = WalkForwardAdvancedConfig(
        symbols=req.symbols,
        data_start=start,
        data_end=end,
        is_months=req.is_months,
        oos_months=req.oos_months,
        step_months=req.step_months,
        mode=req.mode.upper(),
        initial_balance=req.initial_balance,
        optimization_metric=req.optimization_metric.upper(),
    )

    try:
        result = await _wf_engine.run(wf_config)
        return JSONResponse(content={"success": True, "data": result.to_dict()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monte-carlo")
async def run_monte_carlo(req: MonteCarloRequest):
    """Run Monte Carlo simulation on last backtest trades."""
    global _last_mc_result

    if _last_backtest_result is None:
        raise HTTPException(
            status_code=400,
            detail="No backtest result found. Run /run first."
        )

    mc_config = MonteCarloAdvancedConfig(
        n_simulations=req.n_simulations,
        initial_balance=req.initial_balance,
        ruin_threshold_pct=req.ruin_threshold_pct,
        seed=req.seed,
        resampling_method=req.resampling_method.upper(),
    )

    try:
        closed = [t for t in _last_backtest_result.all_trades if t.exit_time is not None]
        result = _mc_sim.run(closed, mc_config)
        _last_mc_result = result
        return JSONResponse(content={"success": True, "data": result.to_dict()})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/html", response_class=HTMLResponse)
async def get_performance_report_html():
    """Generate and return branded HTML performance report."""
    if _last_backtest_result is None:
        return HTMLResponse("<h1>No backtest result. Run /run first.</h1>", status_code=400)
    html = _perf_report.generate_html(_last_backtest_result, _last_mc_result,
                                       title="Performance Report")
    return HTMLResponse(content=html)


@router.get("/report/json")
async def get_performance_report_json():
    """Return JSON performance report."""
    if _last_backtest_result is None:
        raise HTTPException(status_code=400, detail="No backtest result. Run /run first.")
    data = _perf_report.generate_json(_last_backtest_result, _last_mc_result)
    return JSONResponse(content={"success": True, "data": data})


@router.get("/risk-report", response_class=HTMLResponse)
async def get_risk_report_html():
    """Generate and return branded HTML risk report."""
    if _last_backtest_result is None:
        return HTMLResponse("<h1>No backtest result. Run /run first.</h1>", status_code=400)
    html = _risk_report.generate_html(_last_backtest_result, _last_mc_result)
    return HTMLResponse(content=html)


@router.get("/risk-report/json")
async def get_risk_report_json():
    """Return JSON risk report."""
    if _last_backtest_result is None:
        raise HTTPException(status_code=400, detail="No backtest result. Run /run first.")
    data = _risk_report.generate_json(_last_backtest_result, _last_mc_result)
    return JSONResponse(content={"success": True, "data": data})


@router.get("/status")
async def get_engine_status():
    """Return engine status and available datasets."""
    datasets = _provider.list_datasets()
    last_info = None
    if _last_backtest_result:
        last_info = {
            "symbols":      _last_backtest_result.config.symbols,
            "total_trades": _last_backtest_result.total_trades,
            "net_profit":   _last_backtest_result.net_profit,
            "sharpe_ratio": _last_backtest_result.sharpe_ratio,
        }
    return JSONResponse(content={
        "success": True,
        "data": {
            "brand":           "Galaxy Vast Institutional Backtest Engine",
            "version":         "3.0.0",
            "available_datasets": datasets,
            "last_backtest":   last_info,
            "has_mc_result":   _last_mc_result is not None,
            "engines": {
                "multi_symbol_backtest": "READY",
                "parameter_optimizer":  "READY",
                "walk_forward":         "READY",
                "monte_carlo":          "READY",
            },
        }
    })
