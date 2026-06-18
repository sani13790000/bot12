"""Galaxy Vast — Institutional Research API Routes."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.institutional.ai_explainability import ExplainabilityEngine, TradeExplanation
from backend.institutional.correlation_engine import CorrelationEngine
from backend.institutional.data_store import InstitutionalDataStore
from backend.institutional.market_replay import MarketReplayEngine, ReplayConfig, ReplaySpeed, ReplayState
from backend.institutional.monte_carlo import MonteCarloEngine
from backend.institutional.performance_metrics import PerformanceMetrics
from backend.institutional.portfolio_manager import PortfolioManager
from backend.institutional.rl_agent import RLAgentConfig, RLTradingAgent
from backend.institutional.risk_engine import InstitutionalRiskEngine
from backend.institutional.tick_backtest import (
    BacktestOrder,
    SymbolConfig,
    TickBacktestConfig,
    TickBacktestEngine,
    TickData,
)
from backend.institutional.walk_forward import WalkForwardConfig, WalkForwardOptimizer
from backend.research.backtest.engine import BacktestTrade, CandleData

router = APIRouter(prefix="/research/institutional", tags=["institutional"])

# Global replay engine instance (single-user; for multi-user use session-scoped store)
_replay_engine = MarketReplayEngine()


class CandleInput(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_candle(self) -> CandleData:
        return CandleData(
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


class BacktestRequest(BaseModel):
    symbols: List[str] = ["XAUUSD"]
    timeframe: str = "M15"
    initial_balance: float = 100_000.0
    risk_per_trade_pct: float = 1.0
    slippage_pips: float = 0.3
    commission_per_lot: float = 3.5
    spread_pips: float = 0.2
    max_trades_per_day: int = 10
    min_rr_ratio: float = 1.5
    ticks_per_candle: int = 20
    candles_by_symbol: Dict[str, List[CandleInput]]
    signal_generator: Optional[str] = None  # reserved for named strategies


class WalkForwardRequest(BaseModel):
    symbols: List[str] = ["XAUUSD"]
    timeframe: str = "M15"
    train_days: int = 90
    validation_days: int = 30
    test_days: int = 30
    step_days: int = 30
    optimization_metric: str = "sharpe_ratio"
    parameter_grid: Dict[str, List[Any]] = Field(default_factory=dict)
    candles_by_symbol: Dict[str, List[CandleInput]]


class MonteCarloRequest(BaseModel):
    trades: List[Dict[str, Any]]
    initial_balance: float = 100_000.0
    simulations: int = 1000
    ruin_threshold_pct: float = 50.0


class ExplainRequest(BaseModel):
    symbol: str
    signal: Dict[str, Any]
    history: List[CandleInput] = Field(default_factory=list)
    agent_scores: Dict[str, float] = Field(default_factory=dict)


class PortfolioRequest(BaseModel):
    strategy: str = "EQUAL_WEIGHT"
    total_capital: float = 100_000.0
    max_risk_pct: float = 5.0
    signals: List[Dict[str, Any]]


class CorrelationRequest(BaseModel):
    symbols: List[str]
    price_series: Dict[str, List[float]]
    correlation_threshold: float = 0.7


class RLTrainRequest(BaseModel):
    symbol: str = "XAUUSD"
    candles: List[CandleInput]
    timesteps: int = 10_000
    window_size: int = 20


class RLPredictRequest(BaseModel):
    symbol: str = "XAUUSD"
    candles: List[CandleInput]


class ReplayLoadRequest(BaseModel):
    symbol: str = "XAUUSD"
    speed: float = 1.0
    candles: List[CandleInput]


class ReplayControlRequest(BaseModel):
    action: str  # play, pause, resume, stop, step_forward, step_backward
    speed: Optional[float] = None
    index: Optional[int] = None


def _simple_signal_generator(sym: str, tick: TickData, history: List[CandleData]) -> Optional[Dict[str, Any]]:
    """Simple demo signal generator for backtests when none is supplied."""
    if len(history) < 20:
        return None
    closes = [c.close for c in history]
    sma20 = sum(closes[-20:]) / 20
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else sma20
    latest = history[-1]
    atr = max(latest.high - latest.low, abs(latest.high - closes[-2]), abs(latest.low - closes[-2])) if len(closes) > 1 else latest.high - latest.low
    if sma20 > sma50 and latest.close > sma20:
        return {
            "direction": "BUY",
            "entry_price": tick.ask,
            "stop_loss": tick.ask - 1.5 * atr,
            "take_profit": tick.ask + 3.0 * atr,
        }
    elif sma20 < sma50 and latest.close < sma20:
        return {
            "direction": "SELL",
            "entry_price": tick.bid,
            "stop_loss": tick.bid + 1.5 * atr,
            "take_profit": tick.bid - 3.0 * atr,
        }
    return None


@router.post("/backtest")
async def institutional_backtest(request: BacktestRequest) -> Dict[str, Any]:
    try:
        candles = {
            sym: [c.to_candle() for c in clist]
            for sym, clist in request.candles_by_symbol.items()
        }
        config = TickBacktestConfig(
            symbols=request.symbols,
            timeframes=[request.timeframe],
            initial_balance=request.initial_balance,
            risk_per_trade_pct=request.risk_per_trade_pct,
            slippage_pips=request.slippage_pips,
            commission_per_lot=request.commission_per_lot,
            spread_pips=request.spread_pips,
            max_trades_per_day=request.max_trades_per_day,
            min_rr_ratio=request.min_rr_ratio,
            ticks_per_candle=request.ticks_per_candle,
        )
        engine = TickBacktestEngine(config)
        engine.set_signal_generator(_simple_signal_generator)
        result = engine.run(candles, timeframe=request.timeframe)
        await InstitutionalDataStore.save_backtest_result(result, run_name="institutional_api_backtest")
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}") from exc


@router.post("/walk-forward")
async def institutional_walk_forward(request: WalkForwardRequest) -> Dict[str, Any]:
    try:
        candles = {
            sym: [c.to_candle() for c in clist]
            for sym, clist in request.candles_by_symbol.items()
        }
        config = WalkForwardConfig(
            symbols=request.symbols,
            timeframe=request.timeframe,
            train_days=request.train_days,
            validation_days=request.validation_days,
            test_days=request.test_days,
            step_days=request.step_days,
            optimization_metric=request.optimization_metric,
            parameter_grid=request.parameter_grid or WalkForwardOptimizer.DEFAULT_GRID,
        )
        optimizer = WalkForwardOptimizer(config)
        result = optimizer.optimize(candles, _simple_signal_generator)
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Walk-forward failed: {exc}") from exc


@router.post("/monte-carlo")
async def institutional_monte_carlo(request: MonteCarloRequest) -> Dict[str, Any]:
    try:
        trades = [
            BacktestTrade(
                trade_id=t.get("trade_id", ""),
                symbol=t.get("symbol", "XAUUSD"),
                direction=t.get("direction", "BUY"),
                entry_time=t.get("entry_time", ""),
                exit_time=t.get("exit_time", ""),
                entry_price=t.get("entry_price", 0.0),
                exit_price=t.get("exit_price", 0.0),
                stop_loss=t.get("stop_loss", 0.0),
                take_profit=t.get("take_profit", 0.0),
                lot_size=t.get("lot_size", 0.01),
                pnl_pips=t.get("pnl_pips", 0.0),
                pnl_usd=t.get("pnl_usd", 0.0),
                outcome=t.get("outcome", "BE"),
            )
            for t in request.trades
        ]
        engine = MonteCarloEngine(request.initial_balance)
        result = engine.run(trades, simulations=request.simulations, ruin_threshold_pct=request.ruin_threshold_pct)
        return {"success": True, **result.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Monte Carlo failed: {exc}") from exc


@router.post("/explain")
async def institutional_explain(request: ExplainRequest) -> Dict[str, Any]:
    try:
        history = [c.to_candle() for c in request.history]
        engine = ExplainabilityEngine()
        explanation = engine.explain_signal(request.symbol, request.signal, history, request.agent_scores)
        return {"success": True, **explanation.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Explainability failed: {exc}") from exc


@router.post("/portfolio")
async def institutional_portfolio(request: PortfolioRequest) -> Dict[str, Any]:
    try:
        manager = PortfolioManager(request.total_capital, request.max_risk_pct)
        portfolio = manager.build_portfolio(request.signals, strategy=request.strategy)
        return {"success": True, **portfolio.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Portfolio failed: {exc}") from exc


@router.post("/correlation")
async def institutional_correlation(request: CorrelationRequest) -> Dict[str, Any]:
    try:
        import pandas as pd
        price_series = {sym: pd.Series(vals) for sym, vals in request.price_series.items()}
        engine = CorrelationEngine(correlation_threshold=request.correlation_threshold)
        pairs = engine.analyze_pairs(price_series)
        return {"success": True, "pairs": [p.to_dict() for p in pairs]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Correlation failed: {exc}") from exc


@router.post("/rl/train")
async def institutional_rl_train(request: RLTrainRequest) -> Dict[str, Any]:
    try:
        candles = [c.to_candle() for c in request.candles]
        config = RLAgentConfig(symbol=request.symbol, window_size=request.window_size)
        agent = RLTradingAgent(config)
        result = agent.train(candles, timesteps=request.timesteps)
        return {"success": True, **result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RL training failed: {exc}") from exc


@router.post("/rl/predict")
async def institutional_rl_predict(request: RLPredictRequest) -> Dict[str, Any]:
    try:
        candles = [c.to_candle() for c in request.candles]
        config = RLAgentConfig(symbol=request.symbol)
        agent = RLTradingAgent(config)
        action = agent.predict(candles)
        return {"success": True, "action": action, "action_name": ["HOLD", "BUY", "SELL"][action]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RL prediction failed: {exc}") from exc


# --- Market Replay Routes ---

@router.post("/replay/load")
async def replay_load(request: ReplayLoadRequest) -> Dict[str, Any]:
    try:
        candles = [c.to_candle() for c in request.candles]
        speed = ReplaySpeed(request.speed) if request.speed in {1.0, 2.0, 4.0, 10.0} else ReplaySpeed.X1
        config = ReplayConfig(symbol=request.symbol, speed=speed)
        _replay_engine.load_candles(candles, config)
        return {"success": True, "state": _replay_engine.get_state()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Replay load failed: {exc}") from exc


@router.post("/replay/control")
async def replay_control(request: ReplayControlRequest) -> Dict[str, Any]:
    action = request.action.lower()
    try:
        if action == "play":
            # Async play should be run via background task; here we just start it via asyncio.create_task
            import asyncio
            asyncio.create_task(_replay_engine.play())
        elif action == "pause":
            _replay_engine.pause()
        elif action == "resume":
            _replay_engine.resume()
        elif action == "stop":
            _replay_engine.stop()
        elif action == "step_forward":
            frame = _replay_engine.step_forward()
            return {"success": True, "state": _replay_engine.get_state(), "frame": frame.to_dict() if frame else None}
        elif action == "step_backward":
            frame = _replay_engine.step_backward()
            return {"success": True, "state": _replay_engine.get_state(), "frame": frame.to_dict() if frame else None}
        elif action == "jump_to":
            frame = _replay_engine.jump_to(request.index or 0)
            return {"success": True, "state": _replay_engine.get_state(), "frame": frame.to_dict() if frame else None}

        if request.speed:
            speed = ReplaySpeed(request.speed) if request.speed in {1.0, 2.0, 4.0, 10.0} else _replay_engine._config.speed
            _replay_engine.set_speed(speed)

        return {"success": True, "state": _replay_engine.get_state()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Replay control failed: {exc}") from exc


@router.get("/replay/state")
async def replay_state() -> Dict[str, Any]:
    return {"success": True, "state": _replay_engine.get_state()}


@router.get("/replay/frame/{index}")
async def replay_frame(index: int) -> Dict[str, Any]:
    frame = _replay_engine.jump_to(index)
    return {"success": True, "frame": frame.to_dict() if frame else None}


# --- Risk engine route ---

class RiskRequest(BaseModel):
    returns: List[float]
    current_balance: float
    equity_curve: List[float]
    current_exposure_pct: float = 0.0
    max_risk_per_trade_pct: float = 1.0
    max_daily_risk_pct: float = 3.0
    max_drawdown_pct: float = 10.0


@router.post("/risk")
async def institutional_risk(request: RiskRequest) -> Dict[str, Any]:
    try:
        engine = InstitutionalRiskEngine(
            initial_balance=request.current_balance,
            max_risk_per_trade_pct=request.max_risk_per_trade_pct,
            max_daily_risk_pct=request.max_daily_risk_pct,
            max_drawdown_pct=request.max_drawdown_pct,
        )
        assessment = engine.assess(
            request.returns,
            request.current_balance,
            request.equity_curve,
            request.current_exposure_pct,
        )
        return {"success": True, **assessment.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Risk assessment failed: {exc}") from exc
