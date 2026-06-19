"""Institutional API routes — replay, tick backtest, WFO, portfolio, explainability, RL, Monte Carlo."""

from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

router = APIRouter(prefix="/institutional", tags=["institutional"])


# ------------------------------------------------------------------ #
#  Request / Response schemas                                          #
# ------------------------------------------------------------------ #

class BacktestRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    initial_balance: float = 10_000.0
    risk_pct: float = 1.0
    spread_multiplier: float = 1.0
    slippage_pips: float = 0.5
    use_commission: bool = True
    candles: List[Dict[str, Any]] = Field(default_factory=list)


class WFORequest(BaseModel):
    symbol: str = "XAUUSD"
    n_windows: int = 5
    optimization_metric: str = "sharpe_ratio"
    parameter_grid: Dict[str, List[Any]] = Field(default_factory=dict)
    candles: List[Dict[str, Any]] = Field(default_factory=list)


class MonteCarloRequest(BaseModel):
    trade_pnls: List[float]
    initial_balance: float = 10_000.0
    n_simulations: int = 1000
    ruin_threshold_pct: float = 50.0
    seed: Optional[int] = 42


class PortfolioRequest(BaseModel):
    symbols: List[str]
    method: str = "risk_parity"
    initial_capital: float = 100_000.0
    max_position_pct: float = 25.0


class ExplainRequest(BaseModel):
    decision: str
    confidence: float
    smc: Dict[str, Any] = Field(default_factory=dict)
    pa: Dict[str, Any] = Field(default_factory=dict)
    ml: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)


class ReplayCreateRequest(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "M15"
    candles: List[Dict[str, Any]]
    trades: Optional[List[Dict[str, Any]]] = None
    initial_equity: float = 10_000.0


# ------------------------------------------------------------------ #
#  Endpoints                                                           #
# ------------------------------------------------------------------ #

@router.post("/backtest/run")
async def run_backtest(req: BacktestRequest):
    """Run tick-level backtest on provided candles."""
    try:
        from backend.institutional.tick_backtest import TickBacktestEngine, TickBacktestConfig
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
            return {"message": "No candles provided. Pass candles array to run backtest.", "status": "empty"}

        # Simple moving average crossover signal for demo
        def signal_fn(candle, history):
            if len(history) < 50:
                return None
            closes = [c["close"] for c in history]
            ema20 = sum(closes[-20:]) / 20
            ema50 = sum(closes[-50:]) / 50
            if ema20 > ema50 * 1.001:
                return {"direction": "BUY",
                        "stop_loss": candle["close"] - candle.get("atr", 10),
                        "take_profit": candle["close"] + candle.get("atr", 10) * 2}
            elif ema20 < ema50 * 0.999:
                return {"direction": "SELL",
                        "stop_loss": candle["close"] + candle.get("atr", 10),
                        "take_profit": candle["close"] - candle.get("atr", 10) * 2}
            return None

        result = engine.run(req.candles, signal_fn)
        return {
            "total_trades": result.total_trades,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "total_net_profit": result.total_net_profit,
            "total_commission": result.total_commission,
            "total_spread_cost": result.total_spread_cost,
            "final_balance": result.final_balance,
            "recovery_factor": result.recovery_factor,
            "calmar_ratio": result.calmar_ratio,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monte-carlo/run")
async def run_monte_carlo(req: MonteCarloRequest):
    """Run Monte Carlo simulation on trade PnL series."""
    try:
        from backend.institutional.monte_carlo import MonteCarloSimulator
        sim = MonteCarloSimulator(
            n_simulations=req.n_simulations,
            ruin_threshold_pct=req.ruin_threshold_pct,
            seed=req.seed,
        )
        result = sim.run(req.trade_pnls, req.initial_balance)
        return {
            "n_simulations": result.n_simulations,
            "probability_of_ruin": result.probability_of_ruin,
            "probability_of_profit": result.probability_of_profit,
            "median_final_balance": result.median_final_balance,
            "mean_final_balance": result.mean_final_balance,
            "percentile_5": result.percentile_5,
            "percentile_25": result.percentile_25,
            "percentile_75": result.percentile_75,
            "percentile_95": result.percentile_95,
            "expected_max_drawdown_pct": result.expected_max_drawdown_pct,
            "ruin_threshold": result.ruin_threshold,
            "sample_paths_count": len(result.sample_paths),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/explainability/explain")
async def explain_trade(req: ExplainRequest):
    """Generate AI explanation for a trade decision."""
    try:
        from backend.institutional.ai_explainability import (
            AIExplainabilityService, SMCSignal, PASignal, MLSignal, RiskSignal
        )
        smc = SMCSignal(**{k: v for k, v in req.smc.items() if hasattr(SMCSignal(), k) or True})
        # Safe construction
        smc = SMCSignal(
            bos_detected=req.smc.get("bos_detected", False),
            choch_detected=req.smc.get("choch_detected", False),
            order_block_price=req.smc.get("order_block_price"),
            order_block_strength=req.smc.get("order_block_strength", 0.0),
            fvg_detected=req.smc.get("fvg_detected", False),
            fvg_top=req.smc.get("fvg_top"),
            fvg_bottom=req.smc.get("fvg_bottom"),
            liquidity_sweep=req.smc.get("liquidity_sweep", False),
            sweep_level=req.smc.get("sweep_level"),
            in_premium_zone=req.smc.get("in_premium_zone"),
            pd_zone_pct=req.smc.get("pd_zone_pct", 0.0),
            structure_score=req.smc.get("structure_score", 0.0),
        )
        pa = PASignal(
            pattern_name=req.pa.get("pattern_name"),
            pattern_strength=req.pa.get("pattern_strength", 0.0),
            trend_alignment=req.pa.get("trend_alignment", False),
            session_alignment=req.pa.get("session_alignment", False),
        )
        ml = MLSignal(
            prediction=req.ml.get("prediction"),
            confidence=req.ml.get("confidence", 0.0),
            top_features=req.ml.get("top_features", []),
            drift_status=req.ml.get("drift_status", "STABLE"),
        )
        risk = RiskSignal(
            within_daily_limit=req.risk.get("within_daily_limit", True),
            account_risk_pct=req.risk.get("account_risk_pct", 0.0),
            open_trades_count=req.risk.get("open_trades_count", 0),
            session_volatility=req.risk.get("session_volatility", "NORMAL"),
        )
        explanation = AIExplainabilityService.explain(
            decision=req.decision,
            confidence=req.confidence,
            smc=smc, pa=pa, ml=ml, risk=risk,
        )
        return explanation.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/portfolio/allocate")
async def compute_portfolio(req: PortfolioRequest):
    """Compute portfolio allocations."""
    try:
        from backend.institutional.portfolio_manager import PortfolioManager, PortfolioConfig, AllocationMethod
        config = PortfolioConfig(
            symbols=req.symbols,
            initial_capital=req.initial_capital,
            method=AllocationMethod(req.method),
            max_position_pct=req.max_position_pct,
        )
        pm = PortfolioManager(config)
        allocations = pm.compute_allocations(req.initial_capital)
        return {
            "method": req.method,
            "total_capital": req.initial_capital,
            "allocations": [
                {"symbol": a.symbol, "weight": a.weight,
                 "capital_usd": a.capital_usd, "max_lot_size": a.max_lot_size}
                for a in allocations
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/risk/assess")
async def assess_risk(data: Dict[str, Any]):
    """Assess risk for a potential trade."""
    try:
        from backend.institutional.risk_engine import InstitutionalRiskEngine
        engine = InstitutionalRiskEngine(
            initial_equity=data.get("equity", 10000),
            max_risk_pct=data.get("max_risk_pct", 1.0),
        )
        report = engine.assess_trade(
            stop_loss_pips=data.get("stop_loss_pips", 15),
            current_atr=data.get("atr", 10),
            symbol=data.get("symbol", "XAUUSD"),
        )
        return {
            "var_95_usd": report.var_95_usd,
            "var_99_usd": report.var_99_usd,
            "cvar_95_usd": report.cvar_95_usd,
            "recommended_lot": report.recommended_lot,
            "risk_usd": report.risk_usd,
            "risk_pct": report.risk_pct,
            "circuit_breaker_active": report.circuit_breaker_active,
            "volatility_regime": report.volatility_regime,
            "suggested_risk_multiplier": report.suggested_risk_multiplier,
            "daily_limit_hit": report.daily_limit_hit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/correlation/compute")
async def compute_correlation(data: Dict[str, Any]):
    """Compute correlation matrix for symbols."""
    try:
        from backend.institutional.correlation_engine import CorrelationEngine
        engine = CorrelationEngine(threshold=data.get("threshold", 0.75))
        prices = data.get("prices", {})  # {symbol: [price1, price2, ...]}
        for symbol, price_list in prices.items():
            for p in price_list:
                engine.add_price(symbol, p)
        signals = data.get("signals", {})
        result = engine.compute(list(prices.keys()), signals or None)
        return {
            "symbols": result.symbols,
            "correlation_matrix": result.correlation_matrix,
            "high_correlation_pairs": result.high_correlation_pairs,
            "conflict_pairs": result.conflict_pairs,
            "diversification_score": result.diversification_score,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/replay/create")
async def create_replay_session(req: ReplayCreateRequest):
    """Initialize a replay session."""
    try:
        from backend.institutional.market_replay import MarketReplayEngine, Candle, ReplayTrade
        candles = [
            Candle(
                timestamp=c.get("timestamp", 0),
                open=c.get("open", 0),
                high=c.get("high", 0),
                low=c.get("low", 0),
                close=c.get("close", 0),
                volume=c.get("volume", 0),
                symbol=req.symbol,
                timeframe=req.timeframe,
            ) for c in req.candles
        ]
        if not candles:
            raise HTTPException(status_code=400, detail="candles array cannot be empty")

        engine = MarketReplayEngine(candles, initial_equity=req.initial_equity)
        return {
            "status": "created",
            "total_candles": engine.total_candles,
            "symbol": req.symbol,
            "timeframe": req.timeframe,
            "initial_equity": req.initial_equity,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def institutional_health():
    """Health check for all institutional modules."""
    modules = {}
    module_list = [
        ("market_replay", "backend.institutional.market_replay", "MarketReplayEngine"),
        ("tick_backtest", "backend.institutional.tick_backtest", "TickBacktestEngine"),
        ("performance_metrics", "backend.institutional.performance_metrics", "PerformanceMetrics"),
        ("walk_forward", "backend.institutional.walk_forward_optimizer", "WalkForwardOptimizer"),
        ("ai_explainability", "backend.institutional.ai_explainability", "AIExplainabilityService"),
        ("rl_agent", "backend.institutional.rl_agent", "RLTradingAgent"),
        ("portfolio_manager", "backend.institutional.portfolio_manager", "PortfolioManager"),
        ("correlation_engine", "backend.institutional.correlation_engine", "CorrelationEngine"),
        ("monte_carlo", "backend.institutional.monte_carlo", "MonteCarloSimulator"),
        ("risk_engine", "backend.institutional.risk_engine", "InstitutionalRiskEngine"),
        ("data_store", "backend.institutional.data_store", "InstitutionalDataStore"),
    ]
    for name, module_path, class_name in module_list:
        try:
            import importlib
            mod = importlib.import_module(module_path)
            getattr(mod, class_name)
            modules[name] = "ok"
        except Exception as e:
            modules[name] = f"error: {str(e)[:60]}"

    all_ok = all(v == "ok" for v in modules.values())
    return {"status": "healthy" if all_ok else "degraded", "modules": modules}
