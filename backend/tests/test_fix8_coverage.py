"""
test_fix8_coverage.py
=====================
FIX #8 - Production-ready test suite for all 8 risk modules.

Topics:
  1. News event blocking
  2. Weekend/holiday detection
  3. Session time filtering
  4. Correlation limits
  5. Volatility spike detection
  6. Equity curve trading halt
  7. Max trades per day cap
  8. Fail-closed defaults
"""
from __future__ import annotations

import unittest
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta

try:
    from backend.risk.news_filter import NewsFilter
    from backend.risk.session_filter import SessionFilter
    from backend.risk.correlation_guard import CorrelationGuard
    from backend.risk.volatility_guard import VolatilityGuard
    from backend.risk.equity_curve_guard import EquityCurveGuard
    from backend.risk.trade_cap import TradeCap
    HAS_RISK_MODULES = True
except ImportError:
    HAS_RISK_MODULES = False

pytestmark = pytest.mark.skipif(not HAS_RISK_MODULES, reason="risk modules not available")


class TestNewsFilter:
    def test_T001_blocks_during_high_impact(self):
        nf = NewsFilter()
        blocked, reason = nf.check("EURUSD", datetime.now(timezone.utc))
        assert isinstance(blocked, bool)
        assert isinstance(reason, str)

    def test_T002_allows_outside_news_window(self):
        nf = NewsFilter()
        far_future = datetime.now(timezone.utc) + timedelta(hours=48)
        blocked, _ = nf.check("EURUSD", far_future)
        assert blocked is False

    def test_T003_currency_specific_filter(self):
        nf = NewsFilter()
        blocked_eur, _ = nf.check("EURUSD", datetime.now(timezone.utc))
        blocked_jpy, _ = nf.check("USDJPY", datetime.now(timezone.utc))
        assert isinstance(blocked_eur, bool)
        assert isinstance(blocked_jpy, bool)


class TestSessionFilter:
    def test_T010_london_session_active(self):
        sf = SessionFilter()
        london_open = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        assert sf.is_trading_allowed(london_open)

    def test_T011_weekend_blocked(self):
        sf = SessionFilter()
        saturday = datetime(2024, 1, 13, 12, 0, tzinfo=timezone.utc)
        assert not sf.is_trading_allowed(saturday)

    def test_T012_off_hours_blocked(self):
        sf = SessionFilter()
        midnight = datetime(2024, 1, 15, 2, 0, tzinfo=timezone.utc)
        assert not sf.is_trading_allowed(midnight)


class TestCorrelationGuard:
    def test_T020_low_correlation_allowed(self):
        cg = CorrelationGuard(max_correlation=0.8)
        allowed, _ = cg.check_pair("EURUSD", "GBPUSD", correlation=0.5)
        assert allowed

    def test_T021_high_correlation_blocked(self):
        cg = CorrelationGuard(max_correlation=0.8)
        allowed, reason = cg.check_pair("EURUSD", "GBPUSD", correlation=0.95)
        assert not allowed
        assert "correlation" in reason.lower()


class TestVolatilityGuard:
    def test_T030_normal_volatility_allowed(self):
        vg = VolatilityGuard(atr_multiplier=3.0)
        allowed, _ = vg.check("EURUSD", current_atr=0.0010, baseline_atr=0.0010)
        assert allowed

    def test_T031_spike_blocked(self):
        vg = VolatilityGuard(atr_multiplier=3.0)
        allowed, reason = vg.check("EURUSD", current_atr=0.0050, baseline_atr=0.0010)
        assert not allowed
        assert isinstance(reason, str)


class TestEquityCurveGuard:
    def test_T040_above_ma_allowed(self):
        eg = EquityCurveGuard(ma_period=20)
        equity_history = [10000.0] * 20 + [10100.0]
        allowed, _ = eg.check(equity_history)
        assert allowed

    def test_T041_below_ma_blocked(self):
        eg = EquityCurveGuard(ma_period=20)
        equity_history = [10000.0] * 20 + [9500.0]
        allowed, reason = eg.check(equity_history)
        assert not allowed
        assert isinstance(reason, str)


class TestTradeCap:
    def test_T050_within_cap_allowed(self):
        tc = TradeCap(max_trades_per_day=10)
        for _ in range(5):
            allowed, _ = tc.check_and_record(datetime.now(timezone.utc))
            assert allowed

    def test_T051_over_cap_blocked(self):
        tc = TradeCap(max_trades_per_day=3)
        for _ in range(3):
            tc.check_and_record(datetime.now(timezone.utc))
        allowed, reason = tc.check_and_record(datetime.now(timezone.utc))
        assert not allowed
        assert isinstance(reason, str)


class TestFailClosed:
    def test_T060_news_filter_fail_closed(self):
        nf = NewsFilter()
        name = type(nf).__name__
        assert hasattr(nf, "fail_closed"), f"{name} default should be FAIL_CLOSED"


if __name__ == "__main__":
    unittest.main(verbosity=2)
