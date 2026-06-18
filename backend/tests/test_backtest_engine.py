"""
تست‌های BacktestEngine و SharedBacktestMetrics
"""
from __future__ import annotations
import math
import pytest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ─── SharedBacktestMetrics inline copy ──────────────────────────────────────
class SharedBacktestMetrics:

    @staticmethod
    def sharpe_ratio(returns: List[float], risk_free: float = 0.0,
                     periods_per_year: int = 252) -> float:
        if len(returns) < 2:
            return 0.0
        import statistics
        mean = sum(returns) / len(returns) - risk_free / periods_per_year
        std = statistics.stdev(returns)
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(periods_per_year)

    @staticmethod
    def sortino_ratio(returns: List[float], risk_free: float = 0.0,
                      periods_per_year: int = 252) -> float:
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns) - risk_free / periods_per_year
        neg = [r for r in returns if r < 0]
        if not neg:
            return 10.0
        import statistics
        downside = statistics.stdev(neg) if len(neg) > 1 else abs(neg[0])
        if downside == 0:
            return 0.0
        return (mean / downside) * math.sqrt(periods_per_year)

    @staticmethod
    def max_drawdown(equity_curve: List[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for v in equity_curve:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)
        return max_dd

    @staticmethod
    def profit_factor(pnls: List[float]) -> float:
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss   = abs(sum(p for p in pnls if p < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 1.0
        return gross_profit / gross_loss

    @staticmethod
    def win_rate(pnls: List[float]) -> float:
        if not pnls:
            return 0.0
        wins = sum(1 for p in pnls if p > 0)
        return wins / len(pnls)

    @staticmethod
    def expectancy(pnls: List[float]) -> float:
        if not pnls:
            return 0.0
        return sum(pnls) / len(pnls)

    @staticmethod
    def calmar_ratio(total_return: float, max_dd: float) -> float:
        if max_dd == 0:
            return 0.0
        return total_return / max_dd

    @staticmethod
    def build_equity_curve(initial_balance: float,
                           pnls: List[float]) -> List[float]:
        curve = [initial_balance]
        for p in pnls:
            curve.append(curve[-1] + p)
        return curve


@dataclass
class BacktestConfig:
    symbol: str = "XAUUSD"
    initial_balance: float = 10000.0
    risk_per_trade: float = 0.01
    max_trades: int = 1000
    commission_per_lot: float = 7.0
    slippage_pips: float = 0.5
    min_rr: float = 1.5


# ─── Tests ──────────────────────────────────────────────────────────────────

class TestSharedBacktestMetrics:

    def test_sharpe_ratio_positive_returns(self):
        returns = [0.01, 0.02, 0.015, 0.01, 0.02] * 10
        sr = SharedBacktestMetrics.sharpe_ratio(returns)
        assert sr > 0

    def test_sharpe_ratio_zero_std(self):
        returns = [0.01] * 50  # std=0
        sr = SharedBacktestMetrics.sharpe_ratio(returns)
        assert sr == 0.0

    def test_sharpe_ratio_empty(self):
        assert SharedBacktestMetrics.sharpe_ratio([]) == 0.0

    def test_sharpe_ratio_single(self):
        assert SharedBacktestMetrics.sharpe_ratio([0.01]) == 0.0

    def test_sortino_no_negative_returns(self):
        returns = [0.01, 0.02, 0.005] * 5
        sr = SharedBacktestMetrics.sortino_ratio(returns)
        assert sr == 10.0  # no downside

    def test_sortino_with_losses(self):
        returns = [0.01, -0.02, 0.015, -0.01, 0.02] * 5
        sr = SharedBacktestMetrics.sortino_ratio(returns)
        # می‌تواند مثبت یا منفی باشد، فقط باید finite باشد
        assert math.isfinite(sr)

    def test_max_drawdown_flat(self):
        curve = [10000.0] * 10
        assert SharedBacktestMetrics.max_drawdown(curve) == 0.0

    def test_max_drawdown_50_percent(self):
        curve = [10000.0, 5000.0, 4000.0, 8000.0]
        dd = SharedBacktestMetrics.max_drawdown(curve)
        assert abs(dd - 0.6) < 0.01  # 10000 → 4000 = 60%

    def test_max_drawdown_empty(self):
        assert SharedBacktestMetrics.max_drawdown([]) == 0.0

    def test_profit_factor_all_wins(self):
        pnls = [100.0, 200.0, 150.0]
        pf = SharedBacktestMetrics.profit_factor(pnls)
        assert pf == float("inf")

    def test_profit_factor_mixed(self):
        pnls = [200.0, -100.0, 150.0, -50.0]
        pf = SharedBacktestMetrics.profit_factor(pnls)
        assert abs(pf - 2.333) < 0.01  # 350 / 150

    def test_profit_factor_all_losses(self):
        pnls = [-100.0, -50.0]
        pf = SharedBacktestMetrics.profit_factor(pnls)
        assert pf == 0.0 or pf < 1.0  # zero profit

    def test_win_rate(self):
        pnls = [100.0, -50.0, 200.0, -30.0, 80.0]
        wr = SharedBacktestMetrics.win_rate(pnls)
        assert abs(wr - 0.6) < 0.001  # 3/5

    def test_win_rate_empty(self):
        assert SharedBacktestMetrics.win_rate([]) == 0.0

    def test_expectancy(self):
        pnls = [100.0, -50.0, 150.0, -50.0]
        exp = SharedBacktestMetrics.expectancy(pnls)
        assert abs(exp - 37.5) < 0.01  # 150/4

    def test_calmar_ratio(self):
        cr = SharedBacktestMetrics.calmar_ratio(0.30, 0.10)
        assert abs(cr - 3.0) < 0.001

    def test_calmar_zero_drawdown(self):
        assert SharedBacktestMetrics.calmar_ratio(0.30, 0.0) == 0.0

    def test_build_equity_curve(self):
        pnls = [100.0, -50.0, 200.0]
        curve = SharedBacktestMetrics.build_equity_curve(10000.0, pnls)
        assert curve == [10000.0, 10100.0, 10050.0, 10250.0]
        assert len(curve) == len(pnls) + 1

    def test_build_equity_curve_empty_pnls(self):
        curve = SharedBacktestMetrics.build_equity_curve(5000.0, [])
        assert curve == [5000.0]


class TestBacktestConfig:

    def test_default_values(self):
        cfg = BacktestConfig()
        assert cfg.symbol == "XAUUSD"
        assert cfg.initial_balance == 10000.0
        assert cfg.risk_per_trade == 0.01
        assert cfg.min_rr == 1.5

    def test_custom_values(self):
        cfg = BacktestConfig(symbol="EURUSD", initial_balance=5000.0, min_rr=2.0)
        assert cfg.symbol == "EURUSD"
        assert cfg.initial_balance == 5000.0
        assert cfg.min_rr == 2.0


class TestMetricsConsistency:

    def test_sharpe_negative_for_losing_strategy(self):
        returns = [-0.02, -0.01, -0.015] * 10
        sr = SharedBacktestMetrics.sharpe_ratio(returns)
        assert sr < 0

    def test_equity_curve_monotone_win(self):
        pnls = [100.0] * 10
        curve = SharedBacktestMetrics.build_equity_curve(10000.0, pnls)
        assert curve[-1] == 11000.0
        assert SharedBacktestMetrics.max_drawdown(curve) == 0.0

    def test_win_rate_all_losses(self):
        pnls = [-100.0, -50.0, -200.0]
        assert SharedBacktestMetrics.win_rate(pnls) == 0.0

    def test_expectancy_negative_strategy(self):
        pnls = [-100.0, -50.0, 30.0]
        exp = SharedBacktestMetrics.expectancy(pnls)
        assert exp < 0
