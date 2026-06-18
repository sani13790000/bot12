"""Galaxy Vast — Tests for institutional-grade modules."""
import asyncio
from datetime import datetime, timedelta

import numpy as np
import pytest

from backend.institutional.ai_explainability import ExplainabilityEngine
from backend.institutional.correlation_engine import CorrelationEngine
from backend.institutional.market_replay import MarketReplayEngine, ReplayConfig, ReplaySpeed, ReplayState
from backend.institutional.monte_carlo import MonteCarloEngine
from backend.institutional.performance_metrics import PerformanceMetrics
from backend.institutional.portfolio_manager import PortfolioManager
from backend.institutional.risk_engine import InstitutionalRiskEngine
from backend.institutional.tick_backtest import (
    SymbolConfig,
    TickBacktestConfig,
    TickBacktestEngine,
    TickSimulator,
)
from backend.institutional.walk_forward import WalkForwardConfig, WalkForwardOptimizer
from backend.research.backtest.engine import BacktestTrade, CandleData


def _make_candles(n=100, start_price=2350.0):
    candles = []
    price = start_price
    now = datetime.utcnow() - timedelta(hours=n)
    for i in range(n):
        o = price
        h = price * (1 + abs(np.random.normal(0, 0.003)))
        l = price * (1 - abs(np.random.normal(0, 0.003)))
        c = l + (h - l) * np.random.random()
        candles.append(CandleData(
            timestamp=(now + timedelta(hours=i)).isoformat(),
            open=round(o, 2),
            high=round(h, 2),
            low=round(l, 2),
            close=round(c, 2),
            volume=100.0,
        ))
        price = c
    return candles


def _simple_signal(sym, tick, history):
    if len(history) < 20:
        return None
    closes = [c.close for c in history]
    sma20 = sum(closes[-20:]) / 20
    latest = history[-1]
    if latest.close > sma20:
        return {"direction": "BUY", "entry_price": tick.ask, "stop_loss": tick.ask - 2.0, "take_profit": tick.ask + 6.0}
    return {"direction": "SELL", "entry_price": tick.bid, "stop_loss": tick.bid + 2.0, "take_profit": tick.bid - 6.0}


# ---------------------------------------------------------------------------
# Market Replay
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_market_replay_play():
    engine = MarketReplayEngine()
    candles = _make_candles(50)
    engine.load_candles(candles, ReplayConfig(symbol="XAUUSD", speed=ReplaySpeed.INSTANT if hasattr(ReplaySpeed, "INSTANT") else ReplaySpeed.X10))
    frames = []
    engine.register_frame_callback(lambda f: frames.append(f))
    # Use x10 speed to finish quickly
    engine.set_speed(ReplaySpeed.X10)
    session = await engine.play()
    assert session.state in (ReplayState.FINISHED, ReplayState.PLAYING)
    assert len(frames) > 0


def test_market_replay_step():
    engine = MarketReplayEngine()
    candles = _make_candles(30)
    engine.load_candles(candles, ReplayConfig(symbol="XAUUSD"))
    frame = engine.step_forward()
    assert frame is not None
    assert frame.index == 0
    frame2 = engine.step_forward()
    assert frame2.index == 1
    back = engine.step_backward()
    assert back.index == 0


# ---------------------------------------------------------------------------
# Tick Backtest
# ---------------------------------------------------------------------------

def test_tick_simulator():
    candle = CandleData(timestamp="2024-01-01T00:00:00", open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0)
    cfg = SymbolConfig(symbol="XAUUSD", pip_size=0.1, tick_size=0.01, contract_size=100.0, spread_pips=0.2, commission_per_lot=3.5, slippage_pips=0.3, point_value=10.0)
    ticks = TickSimulator.candle_to_ticks(candle, cfg, timeframe="H1", ticks_per_candle=10)
    assert len(ticks) == 10
    assert all(t.bid <= t.ask for t in ticks)


def test_tick_backtest_run():
    candles = _make_candles(100)
    config = TickBacktestConfig(symbols=["XAUUSD"], timeframes=["H1"], initial_balance=10_000.0, risk_per_trade_pct=1.0, max_trades_per_day=50)
    engine = TickBacktestEngine(config)
    engine.set_signal_generator(_simple_signal)
    result = engine.run({"XAUUSD": candles}, timeframe="H1")
    assert "final_balance" in result
    assert "metrics" in result
    assert result["total_trades"] >= 0


# ---------------------------------------------------------------------------
# Performance Metrics
# ---------------------------------------------------------------------------

def test_performance_metrics_empty():
    metrics = PerformanceMetrics([], 10_000.0).to_dict()
    assert metrics["total_trades"] == 0


def test_performance_metrics_with_trades():
    trades = [
        BacktestTrade(trade_id="1", symbol="XAUUSD", direction="BUY", entry_time="", exit_time="", entry_price=100.0, exit_price=105.0, stop_loss=99.0, take_profit=110.0, lot_size=0.1, pnl_pips=50.0, pnl_usd=500.0, outcome="WIN"),
        BacktestTrade(trade_id="2", symbol="XAUUSD", direction="SELL", entry_time="", exit_time="", entry_price=105.0, exit_price=100.0, stop_loss=106.0, take_profit=95.0, lot_size=0.1, pnl_pips=50.0, pnl_usd=500.0, outcome="WIN"),
        BacktestTrade(trade_id="3", symbol="XAUUSD", direction="BUY", entry_time="", exit_time="", entry_price=100.0, exit_price=95.0, stop_loss=99.0, take_profit=110.0, lot_size=0.1, pnl_pips=-50.0, pnl_usd=-500.0, outcome="LOSS"),
    ]
    metrics = PerformanceMetrics(trades, 10_000.0, 11_000.0).to_dict()
    assert metrics["total_trades"] == 3
    assert metrics["win_rate"] == pytest.approx(66.67, 0.01)
    assert metrics["net_profit"] == 500.0


# ---------------------------------------------------------------------------
# Walk-Forward
# ---------------------------------------------------------------------------

def test_walk_forward_optimizer_windows():
    cfg = WalkForwardConfig(train_days=10, validation_days=5, test_days=5, step_days=5)
    opt = WalkForwardOptimizer(cfg)
    start = datetime(2024, 1, 1)
    end = datetime(2024, 2, 15)
    windows = opt.generate_windows(start, end)
    assert len(windows) > 0
    assert windows[0].train_start == start


# ---------------------------------------------------------------------------
# Explainability
# ---------------------------------------------------------------------------

def test_explainability():
    engine = ExplainabilityEngine()
    history = _make_candles(30)
    signal = {"direction": "BUY", "entry_price": 2350.0, "stop_loss": 2340.0, "take_profit": 2370.0, "confidence": 75.0}
    exp = engine.explain_signal("XAUUSD", signal, history, agent_scores={"SMC": 80})
    assert exp.direction == "BUY"
    assert len(exp.reasons) > 0


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

def test_portfolio_equal_weight():
    signals = [
        {"symbol": "XAUUSD", "direction": "BUY", "entry_price": 2350.0, "stop_loss": 2340.0, "take_profit": 2370.0},
        {"symbol": "EURUSD", "direction": "SELL", "entry_price": 1.0850, "stop_loss": 1.0900, "take_profit": 1.0750},
    ]
    manager = PortfolioManager(100_000.0, max_risk_pct=5.0)
    portfolio = manager.build_portfolio(signals, strategy="EQUAL_WEIGHT")
    assert len(portfolio.positions) == 2
    assert sum(p.weight for p in portfolio.positions) == pytest.approx(1.0, 0.01)


# ---------------------------------------------------------------------------
# Correlation
# ---------------------------------------------------------------------------

def test_correlation_engine():
    import pandas as pd
    engine = CorrelationEngine()
    a = pd.Series(np.random.normal(0, 1, 100)).cumsum()
    b = pd.Series(np.random.normal(0, 1, 100)).cumsum()
    pairs = engine.analyze_pairs({"A": a, "B": b})
    assert len(pairs) == 1
    assert -1.0 <= pairs[0].correlation <= 1.0


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def test_monte_carlo():
    trades = [
        BacktestTrade(trade_id="1", symbol="XAUUSD", direction="BUY", entry_time="", exit_time="", entry_price=100.0, exit_price=105.0, stop_loss=99.0, take_profit=110.0, lot_size=0.1, pnl_pips=50.0, pnl_usd=500.0, outcome="WIN"),
        BacktestTrade(trade_id="2", symbol="XAUUSD", direction="BUY", entry_time="", exit_time="", entry_price=100.0, exit_price=95.0, stop_loss=99.0, take_profit=110.0, lot_size=0.1, pnl_pips=-50.0, pnl_usd=-500.0, outcome="LOSS"),
    ] * 20
    engine = MonteCarloEngine(10_000.0)
    result = engine.run(trades, simulations=100)
    assert result.simulations == 100
    assert 0.0 <= result.probability_of_ruin <= 1.0


# ---------------------------------------------------------------------------
# Risk Engine
# ---------------------------------------------------------------------------

def test_risk_engine():
    engine = InstitutionalRiskEngine(100_000.0)
    assessment = engine.assess(
        returns=[-0.01, 0.005, -0.005, 0.01, -0.002],
        current_balance=100_000.0,
        equity_curve=[100_000.0, 99_000.0, 99_500.0, 99_000.0, 100_000.0, 99_800.0],
        current_exposure_pct=2.0,
    )
    assert assessment.var_95 <= 0
    assert assessment.within_limits is True


def test_kelly_position_size():
    engine = InstitutionalRiskEngine(100_000.0)
    size = engine.kelly_position_size(win_rate=0.55, avg_win=120, avg_loss=60, balance=100_000.0)
    assert size > 0
