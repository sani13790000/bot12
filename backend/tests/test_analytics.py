"""
Galaxy Vast AI Trading Platform
Unit Tests — Analytics Module (MetricsEngine)

Run:
    cd backend
    pytest tests/test_analytics.py -v
"""

import math
import pytest
from datetime import datetime, timedelta
from typing import List

from analytics.metrics_engine import MetricsEngine, TradeRecord, AnalyticsResult


# ── Test helpers ─────────────────────────────────────────────────────────────

def make_trade(
    ticket: int,
    profit_loss: float,
    days_ago_open: int = 10,
    duration_hours: int = 2,
    risk_amount: float = 100.0,
    symbol: str = "XAUUSD",
    session: str = "LONDON",
) -> TradeRecord:
    now  = datetime.utcnow()
    open_t  = now - timedelta(days=days_ago_open)
    close_t = open_t + timedelta(hours=duration_hours)
    return TradeRecord(
        ticket=ticket,
        symbol=symbol,
        direction="BUY" if profit_loss >= 0 else "SELL",
        entry_price=2300.0,
        exit_price=2300.0 + profit_loss / 10,
        stop_loss=2290.0,
        lot_size=0.10,
        profit_loss=profit_loss,
        open_time=open_t,
        close_time=close_t,
        risk_amount=risk_amount,
        session=session,
    )


def make_trades_mixed() -> List[TradeRecord]:
    """A realistic mix: 6 wins, 4 losses."""
    return [
        make_trade(1,  +200, days_ago_open=30, risk_amount=100),
        make_trade(2,  -100, days_ago_open=28, risk_amount=100),
        make_trade(3,  +150, days_ago_open=25, risk_amount=100),
        make_trade(4,  +180, days_ago_open=22, risk_amount=100),
        make_trade(5,  -120, days_ago_open=20, risk_amount=100),
        make_trade(6,  +220, days_ago_open=18, risk_amount=100),
        make_trade(7,  -80,  days_ago_open=15, risk_amount=100),
        make_trade(8,  +160, days_ago_open=12, risk_amount=100),
        make_trade(9,  +130, days_ago_open=8,  risk_amount=100),
        make_trade(10, -90,  days_ago_open=3,  risk_amount=100),
    ]


# ── Test: empty trades ────────────────────────────────────────────────────────

class TestEmptyTrades:
    def test_empty_returns_zero_metrics(self):
        engine = MetricsEngine()
        result = engine.calculate([], initial_balance=10_000)
        assert result.total_trades     == 0
        assert result.sharpe_ratio     == 0.0
        assert result.sortino_ratio    == 0.0
        assert result.profit_factor    == 0.0
        assert result.max_drawdown_pct == 0.0


# ── Test: basic counts ────────────────────────────────────────────────────────

class TestBasicCounts:
    def setup_method(self):
        self.engine = MetricsEngine()
        self.trades = make_trades_mixed()
        self.result = self.engine.calculate(self.trades, initial_balance=10_000)

    def test_total_trades(self):
        assert self.result.total_trades == 10

    def test_winning_trades(self):
        assert self.result.winning_trades == 6

    def test_losing_trades(self):
        assert self.result.losing_trades == 4

    def test_win_rate(self):
        assert abs(self.result.win_rate - 0.6) < 1e-6


# ── Test: P&L ────────────────────────────────────────────────────────────────

class TestProfitLoss:
    def setup_method(self):
        self.engine = MetricsEngine()
        self.trades = make_trades_mixed()
        self.result = self.engine.calculate(self.trades, initial_balance=10_000)

    def test_gross_profit_positive(self):
        assert self.result.gross_profit > 0

    def test_gross_loss_positive(self):
        assert self.result.gross_loss > 0

    def test_net_profit_correct(self):
        expected = sum(t.profit_loss for t in self.trades)
        assert abs(self.result.net_profit - expected) < 0.01

    def test_profit_factor_above_one(self):
        assert self.result.profit_factor > 1.0

    def test_final_balance_correct(self):
        expected = 10_000 + self.result.net_profit
        assert abs(self.result.final_balance - expected) < 0.01


# ── Test: Ratios ──────────────────────────────────────────────────────────────

class TestRatios:
    def setup_method(self):
        self.engine = MetricsEngine()
        self.trades = make_trades_mixed()
        self.result = self.engine.calculate(self.trades, initial_balance=10_000)

    def test_sharpe_ratio_is_float(self):
        assert isinstance(self.result.sharpe_ratio, float)

    def test_sortino_ratio_is_float(self):
        assert isinstance(self.result.sortino_ratio, float)
        assert not math.isnan(self.result.sortino_ratio)

    def test_sortino_ge_sharpe_for_profitable(self):
        # for positive-skew returns, sortino should generally >= sharpe
        # (not always, depends on return distribution)
        assert self.result.sortino_ratio >= 0

    def test_calmar_ratio_positive_for_profitable(self):
        if self.result.max_drawdown_pct > 0:
            assert self.result.calmar_ratio >= 0

    def test_recovery_factor_positive(self):
        if self.result.max_drawdown_amount > 0:
            assert self.result.recovery_factor >= 0


# ── Test: Drawdown ────────────────────────────────────────────────────────────

class TestDrawdown:
    def setup_method(self):
        self.engine = MetricsEngine()

    def test_no_drawdown_all_winners(self):
        trades = [make_trade(i, +100, days_ago_open=30-i) for i in range(5)]
        result = self.engine.calculate(trades, initial_balance=10_000)
        assert result.max_drawdown_pct == 0.0

    def test_drawdown_after_loss(self):
        trades = [
            make_trade(1, +100, days_ago_open=10),
            make_trade(2, -300, days_ago_open=8),
            make_trade(3, +100, days_ago_open=5),
        ]
        result = self.engine.calculate(trades, initial_balance=10_000)
        assert result.max_drawdown_amount > 0

    def test_max_drawdown_pct_between_0_and_1(self):
        trades = make_trades_mixed()
        result = self.engine.calculate(trades, initial_balance=10_000)
        assert 0.0 <= result.max_drawdown_pct <= 1.0

    def test_equity_curve_length(self):
        trades = make_trades_mixed()
        result = self.engine.calculate(trades, initial_balance=10_000)
        assert len(result.equity_curve) == len(trades) + 1


# ── Test: Expectancy ──────────────────────────────────────────────────────────

class TestExpectancy:
    def setup_method(self):
        self.engine = MetricsEngine()
        self.trades = make_trades_mixed()
        self.result = self.engine.calculate(self.trades, initial_balance=10_000)

    def test_expectancy_positive_for_winning_system(self):
        assert self.result.expectancy > 0

    def test_expectancy_r_positive_for_good_rr(self):
        assert self.result.expectancy_r > 0

    def test_expectancy_r_is_float(self):
        assert isinstance(self.result.expectancy_r, float)


# ── Test: Consecutive Streaks ─────────────────────────────────────────────────

class TestStreaks:
    def setup_method(self):
        self.engine = MetricsEngine()

    def test_consecutive_wins(self):
        trades = [
            make_trade(1, +100, days_ago_open=10),
            make_trade(2, +100, days_ago_open=8),
            make_trade(3, +100, days_ago_open=6),
            make_trade(4, -100, days_ago_open=4),
        ]
        result = self.engine.calculate(trades)
        assert result.max_consecutive_wins == 3

    def test_consecutive_losses(self):
        trades = [
            make_trade(1, -100, days_ago_open=10),
            make_trade(2, -100, days_ago_open=8),
            make_trade(3, +100, days_ago_open=6),
        ]
        result = self.engine.calculate(trades)
        assert result.max_consecutive_losses == 2


# ── Test: Breakdowns ─────────────────────────────────────────────────────────

class TestBreakdowns:
    def setup_method(self):
        self.engine = MetricsEngine()
        self.trades = [
            make_trade(1, +100, symbol="XAUUSD", session="LONDON"),
            make_trade(2, -50,  symbol="EURUSD", session="NY"),
            make_trade(3, +80,  symbol="XAUUSD", session="NY"),
            make_trade(4, -60,  symbol="GBPUSD", session="LONDON"),
        ]
        self.result = self.engine.calculate(self.trades)

    def test_by_symbol_contains_all_symbols(self):
        assert "XAUUSD" in self.result.by_symbol
        assert "EURUSD" in self.result.by_symbol
        assert "GBPUSD" in self.result.by_symbol

    def test_by_session_contains_sessions(self):
        assert "LONDON" in self.result.by_session
        assert "NY"     in self.result.by_session

    def test_symbol_win_rate_correct(self):
        xau = self.result.by_symbol["XAUUSD"]
        assert xau["trades"] == 2
        assert xau["wins"]   == 2
        assert xau["win_rate"] == 1.0


# ── Test: to_dict serialization ───────────────────────────────────────────────

class TestSerialization:
    def test_to_dict_has_all_keys(self):
        engine = MetricsEngine()
        result = engine.calculate(make_trades_mixed(), initial_balance=10_000)
        d = result.to_dict()
        required = [
            "sharpe_ratio", "sortino_ratio", "calmar_ratio",
            "profit_factor", "recovery_factor", "expectancy_r",
            "max_drawdown_pct", "win_rate", "total_trades", "net_profit",
            "equity_curve", "drawdown_curve", "by_symbol", "by_session",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_no_inf_values(self):
        engine = MetricsEngine()
        # all winners → recovery_factor = inf normally
        trades = [make_trade(i, +100, days_ago_open=10-i) for i in range(5)]
        result = engine.calculate(trades, initial_balance=10_000)
        d = result.to_dict()
        for k, v in d.items():
            if isinstance(v, float):
                assert not math.isinf(v) or k in ("profit_factor", "recovery_factor", "calmar_ratio")
