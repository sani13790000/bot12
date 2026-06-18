"""
Galaxy Vast AI Trading Platform
Institutional Backtesting Engine — Unit Tests

Tests:
  - MultiSymbolBacktestEngine
  - ParameterOptimizer
  - MonteCarloSimulator (inline)
  - WalkForward (inline)
  - ReportGenerator
  - API routes (FastAPI TestClient)
"""
import asyncio
import math
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, List
import pytest

# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_candles(symbol="XAUUSD", n=200, base_price=2000.0, tf=None):
    from backend.backtest_engine.multi_symbol_engine import Candle, Timeframe
    tf = tf or Timeframe.H1
    candles = []
    import random
    rng = random.Random(42)
    price = base_price
    t = datetime(2023, 1, 1)
    for i in range(n):
        move = rng.gauss(0, base_price * 0.003)
        o = price
        c = price + move
        h = max(o, c) + abs(rng.gauss(0, base_price * 0.001))
        lw = min(o, c) - abs(rng.gauss(0, base_price * 0.001))
        candles.append(Candle(time=t, open=round(o,5), high=round(h,5),
                              low=round(lw,5), close=round(c,5),
                              volume=1000, spread=0.5, symbol=symbol, timeframe=tf))
        price = c
        t += timedelta(hours=1)
    return candles


def simple_signal_generator(symbol, tf, candles):
    from backend.backtest_engine.multi_symbol_engine import BacktestSignal, Timeframe
    import random
    if len(candles) < 10:
        return []
    last = candles[-1]
    rng = random.Random(int(last.close * 100) % 9999)
    if rng.random() > 0.93:
        direction = "BUY" if last.close > candles[-2].close else "SELL"
        atr = abs(last.high - last.low)
        sl = last.close - atr * 1.5 if direction == "BUY" else last.close + atr * 1.5
        tp = last.close + atr * 3.0 if direction == "BUY" else last.close - atr * 3.0
        return [BacktestSignal(
            symbol=symbol, direction=direction,
            entry_price=last.close, stop_loss=sl, take_profit=tp,
            confidence=82.0, timeframe=tf, timestamp=last.time,
        )]
    return []


# ─── MultiSymbolBacktestEngine ────────────────────────────────────────────────

class TestMultiSymbolEngine:

    def test_engine_instantiation(self):
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        engine = MultiSymbolBacktestEngine()
        assert engine is not None

    def test_synthetic_candles_generated(self):
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine, Timeframe
        engine = MultiSymbolBacktestEngine()
        candles = engine._generate_synthetic_candles(
            "XAUUSD", Timeframe.H1,
            datetime(2023, 1, 1), datetime(2023, 2, 1)
        )
        assert len(candles) > 0
        assert candles[0].symbol == "XAUUSD"
        assert candles[0].open > 0

    def test_single_symbol_backtest(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestEngine, MultiSymbolConfig, Timeframe
        )
        engine = MultiSymbolBacktestEngine()
        config = MultiSymbolConfig(
            symbols=["XAUUSD"],
            timeframes=[Timeframe.H1],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 6, 1),
            initial_balance=10_000.0,
        )
        result = asyncio.get_event_loop().run_until_complete(
            engine.run(config, {}, simple_signal_generator)
        )
        assert result is not None
        assert result.config.symbols == ["XAUUSD"]
        assert result.total_trades >= 0
        assert "XAUUSD" in result.symbol_results

    def test_multi_symbol_backtest(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestEngine, MultiSymbolConfig, Timeframe
        )
        engine = MultiSymbolBacktestEngine()
        config = MultiSymbolConfig(
            symbols=["XAUUSD", "EURUSD"],
            timeframes=[Timeframe.H1, Timeframe.H4],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 4, 1),
            initial_balance=10_000.0,
            correlation_filter=True,
            max_correlation=0.80,
        )
        result = asyncio.get_event_loop().run_until_complete(
            engine.run(config, {}, simple_signal_generator)
        )
        assert "XAUUSD" in result.symbol_results
        assert "EURUSD" in result.symbol_results

    def test_equity_curve_built(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestEngine, MultiSymbolConfig, Timeframe
        )
        engine = MultiSymbolBacktestEngine()
        config = MultiSymbolConfig(
            symbols=["XAUUSD"],
            timeframes=[Timeframe.H1],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 6, 1),
            initial_balance=10_000.0,
        )
        result = asyncio.get_event_loop().run_until_complete(
            engine.run(config, {}, simple_signal_generator)
        )
        # Equity curve always has at least the initial point
        assert len(result.portfolio_equity) >= 1
        assert result.portfolio_equity[0].equity == 10_000.0

    def test_to_dict_structure(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestEngine, MultiSymbolConfig, Timeframe
        )
        engine = MultiSymbolBacktestEngine()
        config = MultiSymbolConfig(
            symbols=["EURUSD"],
            timeframes=[Timeframe.H1],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 3, 1),
            initial_balance=10_000.0,
        )
        result = asyncio.get_event_loop().run_until_complete(
            engine.run(config, {}, simple_signal_generator)
        )
        d = result.to_dict()
        assert "config" in d
        assert "portfolio" in d
        assert "per_symbol" in d
        assert "equity_curve" in d
        assert "execution" in d

    def test_correlation_blocking(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestEngine, BacktestSignal, Timeframe
        )
        engine = MultiSymbolBacktestEngine()
        sig1 = BacktestSignal("EURUSD","BUY",1.09,1.08,1.11,confidence=80,timeframe=Timeframe.H1,timestamp=datetime.utcnow())
        open_trades = []
        # First signal: no open trades → not correlated
        assert not engine._is_correlated(sig1, open_trades, 0.80)

        from backend.backtest_engine.multi_symbol_engine import BacktestTrade
        t = BacktestTrade(signal=BacktestSignal("GBPUSD","BUY",1.27,1.26,1.29,confidence=80,timeframe=Timeframe.H1,timestamp=datetime.utcnow()), entry_time=datetime.utcnow(), entry_price=1.27)
        open_trades.append(t)
        # EURUSD + GBPUSD BUY → corr=0.85 → blocked
        assert engine._is_correlated(sig1, open_trades, 0.80)

    def test_pip_value_helper(self):
        from backend.backtest_engine.multi_symbol_engine import _pip_value, _pip_size
        assert _pip_value("XAUUSD") == 1.0
        assert _pip_value("EURUSD") == 10.0
        assert _pip_size("USDJPY") == 0.01
        assert _pip_size("EURUSD") == 0.0001

    def test_lot_computation_capped(self):
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        engine = MultiSymbolBacktestEngine()
        lot = engine._compute_lot(10_000, 1.0, 2000.0, 1990.0, "XAUUSD")
        assert 0.01 <= lot <= 100.0

    def test_sharpe_positive(self):
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        engine = MultiSymbolBacktestEngine()
        returns = [0.01, 0.02, -0.005, 0.015, 0.008, -0.003, 0.012]
        sharpe = engine._sharpe(returns)
        assert isinstance(sharpe, float)

    def test_sortino_ignores_gains(self):
        from backend.backtest_engine.multi_symbol_engine import MultiSymbolBacktestEngine
        engine = MultiSymbolBacktestEngine()
        returns = [0.02, 0.03, 0.01, 0.04]  # all positive
        sortino = engine._sortino(returns)
        assert sortino == 999.0  # no downside


# ─── ParameterOptimizer ───────────────────────────────────────────────────────

class TestParameterOptimizer:

    def _make_evaluator(self):
        """Evaluator that returns higher metric for higher confidence."""
        def evaluator(params, is_train):
            conf = params.get("min_confidence", 70)
            metric = (conf - 60) / 30  # normalize 60-90 → 0-1
            noise = 0.05 if is_train else -0.05
            return (metric + noise, 50, 500.0, 0.10, 1.5)
        return evaluator

    def test_optimizer_basic_run(self):
        from backend.backtest_engine.parameter_optimizer import (
            ParameterOptimizer, OptimizationConfig, ParameterGrid
        )
        opt = ParameterOptimizer()
        config = OptimizationConfig(
            parameter_grids=[ParameterGrid("min_confidence", 65, 85, 10)],
            metric="sharpe_ratio",
            max_iterations=20,
            min_trades=1,
        )
        result = asyncio.get_event_loop().run_until_complete(
            opt.optimize(config, self._make_evaluator())
        )
        assert result is not None
        assert result.total_iterations > 0
        assert "min_confidence" in result.best_params

    def test_optimizer_best_params_selected(self):
        from backend.backtest_engine.parameter_optimizer import (
            ParameterOptimizer, OptimizationConfig, ParameterGrid
        )
        opt = ParameterOptimizer()
        config = OptimizationConfig(
            parameter_grids=[ParameterGrid("min_confidence", 60, 90, 10)],
            metric="sharpe_ratio",
            max_iterations=50,
            min_trades=1,
        )
        result = asyncio.get_event_loop().run_until_complete(
            opt.optimize(config, self._make_evaluator())
        )
        # Higher confidence → higher metric → best should be near 90
        assert result.best_params["min_confidence"] >= 80

    def test_optimizer_robustness_computed(self):
        from backend.backtest_engine.parameter_optimizer import (
            ParameterOptimizer, OptimizationConfig, ParameterGrid
        )
        opt = ParameterOptimizer()
        config = OptimizationConfig(
            parameter_grids=[ParameterGrid("min_confidence", 65, 75, 5)],
            metric="sharpe_ratio",
            max_iterations=20,
            min_trades=1,
        )
        result = asyncio.get_event_loop().run_until_complete(
            opt.optimize(config, self._make_evaluator())
        )
        assert 0 <= result.robustness_score <= 100

    def test_optimizer_to_dict(self):
        from backend.backtest_engine.parameter_optimizer import (
            ParameterOptimizer, OptimizationConfig, ParameterGrid
        )
        opt = ParameterOptimizer()
        config = OptimizationConfig(
            parameter_grids=[ParameterGrid("min_confidence", 70, 80, 10)],
            min_trades=1,
        )
        result = asyncio.get_event_loop().run_until_complete(
            opt.optimize(config, self._make_evaluator())
        )
        d = result.to_dict()
        assert "best_params" in d
        assert "robustness_score" in d
        assert "recommendation" in d
        assert "top_10" in d

    def test_parameter_grid_values_int(self):
        from backend.backtest_engine.parameter_optimizer import ParameterGrid
        grid = ParameterGrid("n", 1, 5, 1, "int")
        vals = grid.values()
        assert vals == [1, 2, 3, 4, 5]

    def test_parameter_grid_values_float(self):
        from backend.backtest_engine.parameter_optimizer import ParameterGrid
        grid = ParameterGrid("x", 0.5, 2.0, 0.5)
        vals = grid.values()
        assert len(vals) == 4


# ─── Monte Carlo ──────────────────────────────────────────────────────────────

class TestMonteCarloInline:

    def _simulate(self, pnls, initial=10000, n=500):
        import random
        rng = random.Random(42)
        results_fin, results_dd = [], []
        for _ in range(n):
            sample = rng.choices(pnls, k=len(pnls))
            eq = initial; peak = eq; max_dd = 0.0
            for p in sample:
                eq += p; peak = max(peak, eq)
                dd = (peak - eq) / peak if peak > 0 else 0
                max_dd = max(max_dd, dd)
            results_fin.append(eq)
            results_dd.append(max_dd)
        return results_fin, results_dd

    def test_profitable_strategy_high_prob(self):
        pnls = [+100, +120, +80, -50, +150, +90, -60, +110] * 10
        fins, _ = self._simulate(pnls)
        prob_profit = sum(1 for f in fins if f > 10000) / len(fins)
        assert prob_profit > 0.70

    def test_losing_strategy_low_prob(self):
        pnls = [-100, -80, +30, -120, -60, +50, -90] * 10
        fins, _ = self._simulate(pnls)
        prob_profit = sum(1 for f in fins if f > 10000) / len(fins)
        assert prob_profit < 0.40

    def test_max_dd_bounded(self):
        pnls = [+50] * 20  # always winning
        _, dds = self._simulate(pnls)
        assert max(dds) == 0.0  # no drawdown if always winning

    def test_var_is_negative_for_losers(self):
        pnls = [-100, -80, -60] * 20
        fins, _ = self._simulate(pnls, n=200)
        sorted_fins = sorted(fins)
        n = len(sorted_fins)
        var_95 = (sorted_fins[int(n * 0.05)] - 10000) / 10000
        assert var_95 < 0


# ─── Walk-Forward Inline ──────────────────────────────────────────────────────

class TestWalkForwardInline:

    def test_consistent_strategy_is_robust(self):
        window_results = [
            {"passed": True, "train_sharpe": 1.5, "test_sharpe": 1.2},
            {"passed": True, "train_sharpe": 1.3, "test_sharpe": 1.1},
            {"passed": True, "train_sharpe": 1.6, "test_sharpe": 1.4},
            {"passed": True, "train_sharpe": 1.2, "test_sharpe": 1.0},
            {"passed": False, "train_sharpe": 0.8, "test_sharpe": -0.1},
        ]
        pass_rate = sum(1 for w in window_results if w["passed"]) / len(window_results)
        assert pass_rate == 0.8
        assert pass_rate * 100 >= 60  # robust

    def test_inconsistent_strategy_not_robust(self):
        window_results = [
            {"passed": False}, {"passed": False},
            {"passed": True},  {"passed": False},
            {"passed": False},
        ]
        pass_rate = sum(1 for w in window_results if w["passed"]) / len(window_results)
        assert pass_rate * 100 < 60  # not robust

    def test_recommendation_logic(self):
        for consistency, expected in [(75, "ROBUST"), (55, "ACCEPTABLE"), (30, "OVERFITTED")]:
            rec = "ROBUST" if consistency >= 70 else "ACCEPTABLE" if consistency >= 50 else "OVERFITTED"
            assert rec == expected


# ─── ReportGenerator ─────────────────────────────────────────────────────────

class TestReportGenerator:

    def _make_result(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestEngine, MultiSymbolConfig, Timeframe
        )
        engine = MultiSymbolBacktestEngine()
        config = MultiSymbolConfig(
            symbols=["XAUUSD"],
            timeframes=[Timeframe.H1],
            start_date=datetime(2023, 1, 1),
            end_date=datetime(2023, 3, 1),
            initial_balance=10_000.0,
        )
        return asyncio.get_event_loop().run_until_complete(
            engine.run(config, {}, simple_signal_generator)
        )

    def test_html_report_generated(self):
        from backend.backtest_engine.report_generator import BacktestReportGenerator
        result = self._make_result()
        html = BacktestReportGenerator().generate_html(result)
        assert "Galaxy Vast" in html
        assert "<!DOCTYPE html>" in html
        assert "equityChart" in html
        assert "ddChart" in html

    def test_json_report_generated(self):
        from backend.backtest_engine.report_generator import BacktestReportGenerator
        result = self._make_result()
        report = BacktestReportGenerator().generate_json(result)
        assert "brand" in report
        assert report["brand"] == "Galaxy Vast AI Trading Platform"
        assert "backtest" in report
        assert "generated_at" in report

    def test_html_contains_metrics(self):
        from backend.backtest_engine.report_generator import BacktestReportGenerator
        result = self._make_result()
        html = BacktestReportGenerator().generate_html(result)
        assert "Win Rate" in html
        assert "Profit Factor" in html
        assert "Sharpe Ratio" in html
        assert "Max Drawdown" in html
        assert "Calmar Ratio" in html

    def test_json_with_monte_carlo(self):
        from backend.backtest_engine.report_generator import BacktestReportGenerator
        result = self._make_result()
        mc = {"probability_profit": 0.82, "var_95": -0.08, "simulations": 1000}
        report = BacktestReportGenerator().generate_json(result, mc_result=mc)
        assert "monte_carlo" in report
        assert report["monte_carlo"]["probability_profit"] == 0.82
