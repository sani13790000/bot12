"""tests/test_phase_q.py — Phase Q unit tests (Q-1 through Q-15)"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone


def run(coro):
    return asyncio.run(coro)


# Q-12
from backend.risk.equity_protection import EquityProtectionConfig, EquityProtectionEngine


def test_q12_cooldown_never_negative():
    eng = EquityProtectionEngine(EquityProtectionConfig(cooldown_minutes=60))
    eng.initialize(10000.0)
    eng._state.halt_time = datetime.now(timezone.utc) - timedelta(hours=2)
    assert eng._cooldown_remaining() >= 0.0


def test_q12_no_halt_zero():
    eng = EquityProtectionEngine()
    eng.initialize(10000.0)
    eng._state.halt_time = None
    assert eng._cooldown_remaining() == 0.0


# Q-13
from backend.risk.daily_limits import DailyLimitsEngine, TodayTrades


def test_q13_daily_loss_next_reset():
    r = DailyLimitsEngine(max_daily_loss_pct=2.0).check_limits(10000.0, TodayTrades(1, -250.0, 0.0))
    assert not r.can_trade and r.next_reset is not None


def test_q13_weekly_next_reset():
    r = DailyLimitsEngine(max_weekly_loss_pct=5.0).check_limits(
        10000.0, TodayTrades(1, 0.0, 0.0), week_pnl_usd=-600.0
    )
    assert not r.can_trade and r.next_reset is not None


def test_q13_monthly_next_reset():
    r = DailyLimitsEngine(max_monthly_dd_pct=10.0).check_limits(
        10000.0, TodayTrades(1, 0.0, 0.0), month_pnl_usd=-1100.0
    )
    assert not r.can_trade and r.next_reset is not None


def test_q13_trades_next_reset():
    r = DailyLimitsEngine(max_daily_trades=1).check_limits(10000.0, TodayTrades(1, 0.0, 0.0))
    assert not r.can_trade and r.next_reset is not None


def test_q13_ok_no_next_reset():
    r = DailyLimitsEngine().check_limits(10000.0, TodayTrades(1, 50.0, 0.0))
    assert r.can_trade and r.next_reset is None


# Q-11
from backend.risk.exposure_control import ExposureControlEngine, ExposurePosition


def test_q11_symbols_count():
    eng = ExposureControlEngine()
    assert len(eng._SYMBOL_CURRENCIES) >= 36


def test_q11_majors_present():
    eng = ExposureControlEngine()
    for sym in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]:
        assert sym in eng._SYMBOL_CURRENCIES


def test_q11_block_same_direction():
    eng = ExposureControlEngine()
    pos = [ExposurePosition("EURUSD", "BUY", 1.0)]
    assert not eng.check("EURUSD", "BUY", 1.0, pos).can_trade


# Q-15
from backend.backtest_engine.walk_forward_advanced import WalkForwardAdvanced, _safe_div


def test_q15_safe_div_zero():
    assert _safe_div(5.0, 0.0) == 0.0


def test_q15_safe_div_normal():
    assert abs(_safe_div(6.0, 3.0) - 2.0) < 1e-9


def test_q15_safe_div_custom():
    assert _safe_div(1.0, 0.0, -1.0) == -1.0


def test_q15_no_zero_division():
    class ZR:
        sharpe_ratio = 0.0
        profit_factor = 0.0
        win_rate = 0.0
        net_profit_pct = 0.0
        total_trades = 5
        max_drawdown_pct = 5.0

    class GR:
        sharpe_ratio = 1.5
        profit_factor = 1.8
        win_rate = 0.6
        net_profit_pct = 12.0
        total_trades = 20
        max_drawdown_pct = 4.0

    async def mock_bt(a, b, c, d):
        return ZR(), GR()

    wf = WalkForwardAdvanced(is_months=3, oos_months=1, step_months=1)
    result = run(
        wf.run(
            datetime(2023, 1, 1, tzinfo=timezone.utc),
            datetime(2023, 12, 31, tzinfo=timezone.utc),
            mock_bt,
        )
    )
    for w in result.windows:
        assert w.efficiency >= 0.0


# Q-4
def test_q4_cache_key_per_user():
    from backend.services.decision_service import DecisionService

    ds = DecisionService.__new__(DecisionService)
    ds._cache = {}
    ds._cache_max = 256
    k1 = ds._cache_key("u1", "EURUSD", "BUY")
    k2 = ds._cache_key("u2", "EURUSD", "BUY")
    assert k1 != k2
    k3 = ds._cache_key("u1", "EURUSD", "BUY")
    assert k1 == k3
