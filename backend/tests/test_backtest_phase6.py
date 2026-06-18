"""
Phase 6 Backtest Validity Tests

Tests:
  - Lookahead bias fix: signal receives only past candles
  - ParameterRange discrete values
  - MultiSymbolBacktestResult compat fields
  - SharedBacktestMetrics correctness
  - BacktestEngine bar-by-bar correctness
"""
import pytest
from unittest.mock import MagicMock


# ================================================================
# Fixtures
# ================================================================

@pytest.fixture
def candle_data_class():
    from backend.research.backtest.engine import CandleData
    return CandleData


@pytest.fixture
def backtest_engine():
    from backend.research.backtest.engine import BacktestEngine, BacktestConfig
    return BacktestEngine(BacktestConfig(symbol='XAUUSD', initial_balance=10000.0))


@pytest.fixture
def sample_candles(candle_data_class):
    """50 simple ascending candles."""
    candles = []
    price = 2000.0
    for i in range(50):
        candles.append(candle_data_class(
            timestamp=f'2024-01-{i+1:02d}T00:00:00',
            open=price, high=price + 5, low=price - 5, close=price + 1,
        ))
        price += 1
    return candles


# ================================================================
# Lookahead Bias Tests
# ================================================================

class TestLookaheadBias:
    def test_signal_receives_only_past_candles(self, backtest_engine, sample_candles):
        """Critical: signal_fn must NOT see current candle in history."""
        seen_history_lengths = []

        def signal_fn(candle, history):
            seen_history_lengths.append(len(history))
            return None  # no trades

        backtest_engine.run(sample_candles, signal_fn)

        # First candle: history is empty (candle not yet appended)
        assert seen_history_lengths[0] == 0, "First call must have empty history"
        # Second candle: history has 1 (only first candle)
        assert seen_history_lengths[1] == 1, "Second call must have 1 history item"
        # 51st candle: history has max 50
        assert seen_history_lengths[-1] <= 50

    def test_signal_cannot_see_future_close(self, backtest_engine, sample_candles):
        """Signal at candle[i] must not see candle[i].close in history."""
        received_last_closes = []

        def signal_fn(candle, history):
            if history:
                received_last_closes.append(history[-1].close)
            return None

        backtest_engine.run(sample_candles, signal_fn)

        # The last close in history at candle[i] should be candle[i-1].close
        for idx, last_close in enumerate(received_last_closes):
            expected_close = sample_candles[idx].close  # candle[idx] = previous candle
            assert last_close == expected_close, (
                f"Lookahead bias at position {idx+1}: "
                f"got {last_close}, expected {expected_close}"
            )


# ================================================================
# ParameterRange Tests
# ================================================================

class TestParameterRange:
    def test_values_returns_discrete_list(self):
        from backend.backtest_engine.parameter_optimizer import ParameterRange
        pr = ParameterRange("rr_ratio", [1.5, 2.0, 2.5, 3.0])
        assert pr.values() == [1.5, 2.0, 2.5, 3.0]

    def test_name_stored_correctly(self):
        from backend.backtest_engine.parameter_optimizer import ParameterRange
        pr = ParameterRange("min_confidence", [60.0, 65.0, 70.0])
        assert pr.name == "min_confidence"

    def test_parameter_range_in_optimization_config(self):
        from backend.backtest_engine.parameter_optimizer import ParameterRange, OptimizationConfig
        pr = ParameterRange("test_param", [1, 2, 3])
        cfg = OptimizationConfig(parameter_ranges=[pr])
        assert len(cfg.parameter_ranges) == 1
        assert cfg.parameter_ranges[0].values() == [1, 2, 3]

    def test_generate_combinations_uses_parameter_ranges(self):
        from backend.backtest_engine.parameter_optimizer import (
            ParameterRange, OptimizationConfig, ParameterOptimizer
        )
        optimizer = ParameterOptimizer()
        cfg = OptimizationConfig(
            parameter_ranges=[
                ParameterRange("a", [1, 2]),
                ParameterRange("b", [10, 20]),
            ]
        )
        combos = optimizer._generate_combinations(cfg)
        assert len(combos) == 4  # 2 x 2
        assert {'a': 1, 'b': 10} in combos
        assert {'a': 2, 'b': 20} in combos


# ================================================================
# MultiSymbolBacktestResult Compat Tests
# ================================================================

class TestMultiSymbolResultCompat:
    def test_has_net_profit_pct_field(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestResult, MultiSymbolBacktestConfig
        )
        cfg = MultiSymbolBacktestConfig()
        result = MultiSymbolBacktestResult(config=cfg)
        assert hasattr(result, 'net_profit_pct')
        assert result.net_profit_pct == 0.0

    def test_has_sharpe_ratio_field(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestResult, MultiSymbolBacktestConfig
        )
        cfg = MultiSymbolBacktestConfig()
        result = MultiSymbolBacktestResult(config=cfg)
        assert hasattr(result, 'sharpe_ratio')

    def test_has_win_rate_field(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestResult, MultiSymbolBacktestConfig
        )
        cfg = MultiSymbolBacktestConfig()
        result = MultiSymbolBacktestResult(config=cfg)
        assert hasattr(result, 'win_rate')

    def test_has_profit_factor_field(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestResult, MultiSymbolBacktestConfig
        )
        result = MultiSymbolBacktestResult(config=MultiSymbolBacktestConfig())
        assert hasattr(result, 'profit_factor')

    def test_has_max_drawdown_pct_field(self):
        from backend.backtest_engine.multi_symbol_engine import (
            MultiSymbolBacktestResult, MultiSymbolBacktestConfig
        )
        result = MultiSymbolBacktestResult(config=MultiSymbolBacktestConfig())
        assert hasattr(result, 'max_drawdown_pct')


# ================================================================
# SharedBacktestMetrics Tests
# ================================================================

class TestSharedBacktestMetrics:
    def test_sharpe_positive_returns(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        returns = [0.01] * 100
        assert SharedBacktestMetrics.sharpe_ratio(returns) > 0

    def test_sharpe_empty_returns(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        assert SharedBacktestMetrics.sharpe_ratio([]) == 0.0

    def test_sortino_no_downside(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        returns = [0.01] * 50
        assert SharedBacktestMetrics.sortino_ratio(returns) == float('inf')

    def test_max_drawdown_flat_equity(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        equity = [10000.0] * 10
        dd_pct, dd_abs = SharedBacktestMetrics.max_drawdown(equity)
        assert dd_pct == 0.0
        assert dd_abs == 0.0

    def test_max_drawdown_50pct_drop(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        equity = [10000.0, 5000.0]
        dd_pct, dd_abs = SharedBacktestMetrics.max_drawdown(equity)
        assert dd_pct == 50.0
        assert dd_abs == 5000.0

    def test_profit_factor_no_losses(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        assert SharedBacktestMetrics.profit_factor(1000, 0) == float('inf')

    def test_win_rate_calculation(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        assert SharedBacktestMetrics.win_rate(6, 10) == 60.0

    def test_calmar_ratio_positive(self):
        from backend.research.backtest.engine import SharedBacktestMetrics
        returns = [0.005] * 252
        calmar = SharedBacktestMetrics.calmar_ratio(returns)
        assert calmar > 0


# ================================================================
# OptimizationResult compat
# ================================================================

class TestOptimizationResultCompat:
    def test_has_best_fitness(self):
        from backend.backtest_engine.parameter_optimizer import (
            OptimizationResult, OptimizationConfig
        )
        from datetime import datetime
        result = OptimizationResult(
            config=OptimizationConfig(),
            best_params={}, best_train_metric=0, best_test_metric=0,
            best_combined_score=0, all_iterations=[], total_iterations=0,
            is_robust=False, robustness_score=0, overfit_warning=False,
            recommendation='', best_fitness=0.75,
        )
        assert result.best_fitness == 0.75

    def test_has_best_oos_result(self):
        from backend.backtest_engine.parameter_optimizer import (
            OptimizationResult, OptimizationConfig
        )
        from datetime import datetime
        result = OptimizationResult(
            config=OptimizationConfig(),
            best_params={}, best_train_metric=0, best_test_metric=0,
            best_combined_score=0, all_iterations=[], total_iterations=0,
            is_robust=False, robustness_score=0, overfit_warning=False,
            recommendation='', best_oos_result=None,
        )
        assert hasattr(result, 'best_oos_result')
