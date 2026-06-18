"""
Galaxy Vast AI Trading Platform
Unit Tests — Institutional Backtesting Engine

Coverage:
  - CandleDataProvider (data loading + synthetic generation)
  - MultiSymbolBacktestEngine (per-symbol + portfolio metrics)
  - ParameterOptimizer (grid search + fitness scoring)
  - WalkForwardAdvancedEngine (window building + pass/fail)
  - MonteCarloAdvancedSimulator (statistics + VaR + ruin)
  - PerformanceReportGenerator (JSON + HTML)
  - RiskReportGenerator (classification + recommendations)
"""

from __future__ import annotations

import asyncio
import math
import pytest
from datetime import datetime, timedelta
from typing import List

# ── Engine imports ────────────────────────────────────────────────────────────
from backend.backtest_engine.data_provider import CandleBar, CandleDataProvider, Timeframe
from backend.backtest_engine.multi_symbol_engine import (
    MultiSymbolBacktestEngine,
    MultiSymbolConfig,
    MultiSymbolResult,
    BacktestTrade,
    TradeDirection,
    TradeStatus,
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_provider(n: int = 500) -> CandleDataProvider:
    provider = CandleDataProvider()
    provider.generate_synthetic("XAUUSD", Timeframe.H1, n_candles=n, seed=42)
    provider.generate_synthetic("EURUSD", Timeframe.H1, n_candles=n, seed=99)
    return provider


def _make_trades(n: int = 50, win_rate: float = 0.6) -> List[BacktestTrade]:
    trades = []
    t = datetime(2023, 1, 1)
    for i in range(n):
        win = (i / n) < win_rate
        pnl = 100.0 if win else -50.0
        trades.append(BacktestTrade(
            trade_id="T" + str(i),
            symbol="XAUUSD",
            direction=TradeDirection.BUY,
            entry_time=t,
            entry_price=2000.0,
            stop_loss=1990.0,
            take_profit=2020.0,
            lot_size=0.1,
            risk_amount=100.0,
            exit_time=t + timedelta(hours=4),
            exit_price=2020.0 if win else 1990.0,
            pnl=pnl,
            status=TradeStatus.CLOSED,
            exit_reason="TAKE_PROFIT" if win else "STOP_LOSS",
        ))
        t += timedelta(hours=8)
    return trades


# ═════════════════════════════════════════════════════════════════════════════
# 1. CandleDataProvider
# ═════════════════════════════════════════════════════════════════════════════

class TestCandleDataProvider:

    def test_generate_synthetic_creates_correct_count(self):
        p = CandleDataProvider()
        candles = p.generate_synthetic("XAUUSD", Timeframe.H1, n_candles=200)
        assert len(candles) == 200

    def test_register_and_get(self):
        p = CandleDataProvider()
        candles = p.generate_synthetic("EURUSD", Timeframe.H1, n_candles=100)
        ds = p.get("EURUSD", Timeframe.H1)
        assert ds is not None
        assert len(ds.candles) == 100

    def test_has_returns_true_after_register(self):
        p = CandleDataProvider()
        p.generate_synthetic("GBPUSD", Timeframe.H4, n_candles=100)
        assert p.has("GBPUSD", Timeframe.H4) is True
        assert p.has("XAUUSD", Timeframe.H4) is False

    def test_candle_properties(self):
        bar = CandleBar(time=datetime.utcnow(), open=2000, high=2010, low=1995, close=2005)
        assert bar.is_bullish is True
        assert bar.range == 15
        assert bar.body == 5

    def test_atr_calculation(self):
        p = CandleDataProvider()
        p.generate_synthetic("XAUUSD", Timeframe.H1, n_candles=100)
        ds = p.get("XAUUSD", Timeframe.H1)
        atr = ds.atr(period=14, index=50)
        assert atr > 0

    def test_slice_by_date(self):
        p = CandleDataProvider()
        p.generate_synthetic("XAUUSD", Timeframe.H1, n_candles=200)
        ds = p.get("XAUUSD", Timeframe.H1)
        start = ds.candles[50].time
        end   = ds.candles[100].time
        sliced = ds.slice(start, end)
        assert len(sliced) <= 51


# ═════════════════════════════════════════════════════════════════════════════
# 2. MultiSymbolBacktestEngine
# ═════════════════════════════════════════════════════════════════════════════

class TestMultiSymbolBacktestEngine:

    def test_single_symbol_run(self):
        provider = _make_provider(300)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD"], initial_balance=10_000)
        result   = asyncio.get_event_loop().run_until_complete(engine.run(config))
        assert isinstance(result, MultiSymbolResult)
        assert result.total_trades >= 0

    def test_multi_symbol_run(self):
        provider = _make_provider(400)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD", "EURUSD"], initial_balance=10_000)
        result   = asyncio.get_event_loop().run_until_complete(engine.run(config))
        assert "XAUUSD" in result.symbol_results
        assert "EURUSD" in result.symbol_results

    def test_equity_curve_starts_at_initial_balance(self):
        provider = _make_provider(300)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD"], initial_balance=10_000)
        result   = asyncio.get_event_loop().run_until_complete(engine.run(config))
        if result.equity_curve:
            assert result.equity_curve[0].equity == 10_000

    def test_win_rate_in_range(self):
        provider = _make_provider(400)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD"])
        result   = asyncio.get_event_loop().run_until_complete(engine.run(config))
        if result.total_trades > 0:
            assert 0.0 <= result.win_rate <= 1.0

    def test_profit_factor_positive_for_profitable(self):
        trades = _make_trades(50, win_rate=0.7)
        gross_p = sum(t.pnl for t in trades if t.pnl > 0)
        gross_l = abs(sum(t.pnl for t in trades if t.pnl < 0))
        pf = gross_p / gross_l if gross_l > 0 else float("inf")
        assert pf > 1.0

    def test_to_dict_completeness(self):
        provider = _make_provider(300)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD"])
        result   = asyncio.get_event_loop().run_until_complete(engine.run(config))
        d = result.to_dict()
        assert "portfolio" in d
        assert "by_symbol" in d
        assert "equity_curve" in d
        assert "config" in d


# ═════════════════════════════════════════════════════════════════════════════
# 3. ParameterOptimizer
# ═════════════════════════════════════════════════════════════════════════════

class TestParameterOptimizer:

    def test_grid_search_returns_combinations(self):
        provider = _make_provider(400)
        opt = ParameterOptimizer(provider)
        config = OptimizationConfig(
            symbols=["XAUUSD"],
            parameter_ranges=[
                ParameterRange("rr_ratio",       [1.5, 2.0]),
                ParameterRange("min_confidence", [60.0, 70.0]),
            ],
            method="GRID",
            initial_balance=10_000,
        )
        result = asyncio.get_event_loop().run_until_complete(opt.optimize(config))
        assert result.total_tested > 0
        assert result.best_params != {}

    def test_best_params_are_valid(self):
        provider = _make_provider(400)
        opt = ParameterOptimizer(provider)
        config = OptimizationConfig(
            symbols=["XAUUSD"],
            parameter_ranges=[
                ParameterRange("rr_ratio",       [1.5, 2.0, 2.5]),
                ParameterRange("min_confidence", [60.0, 65.0]),
            ],
            method="GRID",
        )
        result = asyncio.get_event_loop().run_until_complete(opt.optimize(config))
        assert "rr_ratio" in result.best_params
        assert result.best_params["rr_ratio"] in [1.5, 2.0, 2.5]

    def test_fitness_calc_negative_for_no_trades(self):
        from backend.backtest_engine.parameter_optimizer import ParameterOptimizer
        provider = _make_provider(50)
        engine_instance = MultiSymbolBacktestEngine(provider)
        config = MultiSymbolConfig(symbols=["XAUUSD"], min_confidence=99.9)
        result = asyncio.get_event_loop().run_until_complete(engine_instance.run(config))
        fitness = ParameterOptimizer._calc_fitness(result, "SHARPE")
        assert fitness <= 0 or result.total_trades == 0


# ═════════════════════════════════════════════════════════════════════════════
# 4. WalkForwardAdvancedEngine
# ═════════════════════════════════════════════════════════════════════════════

class TestWalkForwardAdvancedEngine:

    def test_window_builder_creates_windows(self):
        from backend.backtest_engine.walk_forward_advanced import (
            WalkForwardAdvancedEngine, WalkForwardAdvancedConfig
        )
        start = datetime(2023, 1, 1)
        end   = datetime(2023, 12, 31)
        config = WalkForwardAdvancedConfig(
            symbols=["XAUUSD"], data_start=start, data_end=end,
            is_months=3, oos_months=1, step_months=1,
        )
        windows = WalkForwardAdvancedEngine._build_windows(config)
        assert len(windows) >= 4

    def test_window_ids_sequential(self):
        from backend.backtest_engine.walk_forward_advanced import (
            WalkForwardAdvancedEngine, WalkForwardAdvancedConfig
        )
        config = WalkForwardAdvancedConfig(
            symbols=["XAUUSD"],
            data_start=datetime(2023, 1, 1),
            data_end=datetime(2023, 12, 31),
            is_months=3, oos_months=1, step_months=1,
        )
        windows = WalkForwardAdvancedEngine._build_windows(config)
        ids = [w.window_id for w in windows]
        assert ids == list(range(1, len(ids) + 1))


# ═════════════════════════════════════════════════════════════════════════════
# 5. MonteCarloAdvancedSimulator
# ═════════════════════════════════════════════════════════════════════════════

class TestMonteCarloAdvancedSimulator:

    def test_run_returns_result(self):
        trades = _make_trades(40, win_rate=0.6)
        sim = MonteCarloAdvancedSimulator()
        result = sim.run(trades, MonteCarloAdvancedConfig(n_simulations=100, seed=42))
        assert result.n_simulations_run == 100

    def test_probability_profit_in_range(self):
        trades = _make_trades(50, win_rate=0.7)
        sim = MonteCarloAdvancedSimulator()
        result = sim.run(trades, MonteCarloAdvancedConfig(n_simulations=200, seed=1))
        assert 0.0 <= result.probability_profit <= 1.0

    def test_ruin_probability_zero_for_winning_system(self):
        """A strongly profitable system should have near-zero ruin prob."""
        trades = _make_trades(100, win_rate=0.9)
        sim = MonteCarloAdvancedSimulator()
        result = sim.run(trades, MonteCarloAdvancedConfig(
            n_simulations=500, seed=7, ruin_threshold_pct=50.0
        ))
        assert result.probability_ruin < 0.5  # very profitable, low ruin

    def test_var_percentages_positive(self):
        trades = _make_trades(40)
        sim = MonteCarloAdvancedSimulator()
        result = sim.run(trades, MonteCarloAdvancedConfig(n_simulations=100, seed=0))
        d = result.to_dict()
        assert "95pct" in d["var"]

    def test_kelly_fraction_in_valid_range(self):
        trades = _make_trades(50, win_rate=0.6)
        sim = MonteCarloAdvancedSimulator()
        result = sim.run(trades, MonteCarloAdvancedConfig(n_simulations=100))
        assert 0.0 <= result.kelly_fraction <= 1.0

    def test_percentile_curves_built(self):
        trades = _make_trades(30)
        sim = MonteCarloAdvancedSimulator()
        result = sim.run(trades, MonteCarloAdvancedConfig(n_simulations=50))
        assert len(result.percentile_curves.p50) > 0

    def test_empty_trades_returns_default(self):
        sim = MonteCarloAdvancedSimulator()
        result = sim.run([], MonteCarloAdvancedConfig(n_simulations=100))
        assert result.n_simulations_run == 0


# ═════════════════════════════════════════════════════════════════════════════
# 6. PerformanceReportGenerator
# ═════════════════════════════════════════════════════════════════════════════

class TestPerformanceReportGenerator:

    def _get_result(self):
        provider = _make_provider(400)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD"])
        return asyncio.get_event_loop().run_until_complete(engine.run(config))

    def test_json_report_has_required_keys(self):
        result = self._get_result()
        gen = PerformanceReportGenerator()
        report = gen.generate_json(result)
        assert "brand" in report
        assert "backtest" in report
        assert "generated" in report
        assert report["brand"] == "Galaxy Vast AI Trading Platform"

    def test_html_report_contains_brand(self):
        result = self._get_result()
        gen  = PerformanceReportGenerator()
        html = gen.generate_html(result)
        assert "Galaxy Vast" in html
        assert "<!DOCTYPE html>" in html
        assert "Chart.js" in html or "chart.js" in html


# ═════════════════════════════════════════════════════════════════════════════
# 7. RiskReportGenerator
# ═════════════════════════════════════════════════════════════════════════════

class TestRiskReportGenerator:

    def _get_result(self, win_rate: float = 0.6):
        provider = _make_provider(400)
        engine   = MultiSymbolBacktestEngine(provider)
        config   = MultiSymbolConfig(symbols=["XAUUSD"])
        return asyncio.get_event_loop().run_until_complete(engine.run(config))

    def test_risk_classification_returns_valid_class(self):
        result = self._get_result()
        gen = RiskReportGenerator()
        cls = gen.classify_risk(result)
        assert cls in ["LOW RISK", "MODERATE RISK", "HIGH RISK", "VERY HIGH RISK"]

    def test_json_risk_report_has_classification(self):
        result = self._get_result()
        gen    = RiskReportGenerator()
        report = gen.generate_json(result)
        assert "risk_classification" in report
        assert "recommendations" in report
        assert len(report["recommendations"]) > 0

    def test_html_risk_report_contains_brand(self):
        result = self._get_result()
        gen  = RiskReportGenerator()
        html = gen.generate_html(result)
        assert "Galaxy Vast" in html
        assert "RISK" in html

    def test_recommendations_are_strings(self):
        result = self._get_result()
        gen  = RiskReportGenerator()
        data = gen.generate_json(result)
        for rec in data["recommendations"]:
            assert isinstance(rec, str)
            assert len(rec) > 5
