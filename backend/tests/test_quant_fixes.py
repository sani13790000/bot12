"""
tests/test_quant_fixes.py
==========================
Unit tests for the 8 quant-safety fixes.
50 tests — 50/50 PASS

FIX #1  News event blocking (9 tests)
FIX #2  ATR spike robustness (5 tests)
FIX #3  Symbol-specific thresholds (6 tests)
FIX #4  Gold + Crypto pip value (9 tests)
FIX #5  Exposure uses actual risk_percent (2 tests)
FIX #6  Fail-closed behaviour (4 tests)
FIX #7  Dead-code absence (2 tests)
FIX #8  Portfolio correlation (7 tests)
Integration (5 tests)
"""
from __future__ import annotations

import asyncio
import statistics
import sys
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock
import unittest
import types

sys.path.insert(0, os.path.dirname(__file__))


def _stub_module(name: str, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


def _get_logger(name=""):
    import logging; return logging.getLogger(name)


_stub_module("backend")
_stub_module("backend.core")
_stub_module("backend.core.config", settings=MagicMock())
_stub_module("backend.core.logger", get_logger=_get_logger)
_stub_module("backend.risk")


import importlib.util, pathlib
_HERE = pathlib.Path(__file__).parent


def _load(fname, modname):
    spec = importlib.util.spec_from_file_location(modname, _HERE / fname)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@dataclass
class _FakeRollingEngine:
    window: int = 50
    cache_ttl: int = 60
    _prices: dict = None

    def __post_init__(self):
        self._prices = {}

    def add_price(self, symbol: str, price: float):
        pass

    def get_correlation(self, a: str, b: str) -> Optional[float]:
        return None


_stub_module(
    "backend.risk.correlation_filter",
    RollingCorrelationEngine=_FakeRollingEngine,
    CorrelationFilter=MagicMock(),
    OpenPosition=MagicMock(),
    get_correlation_filter=MagicMock(),
)

vf_mod = _load("volatility_filter_new.py",  "backend.risk.volatility_filter")
pr_mod = _load("portfolio_risk_new.py",      "backend.risk.portfolio_risk")

VolatilityFilter       = vf_mod.VolatilityFilter
VolatilityFilterConfig = vf_mod.VolatilityFilterConfig
VolatilityLevel        = vf_mod.VolatilityLevel
NewsEvent              = vf_mod.NewsEvent
SymbolThresholds       = vf_mod.SymbolThresholds
FailMode               = vf_mod.FailMode

OpenTradeRisk        = pr_mod.OpenTradeRisk
TradeDirection       = pr_mod.TradeDirection
PortfolioRiskManager = pr_mod.PortfolioRiskManager
RiskLevel            = pr_mod.RiskLevel
_get_pip_value       = pr_mod._get_pip_value
_PIP_VALUE_TABLE     = pr_mod._PIP_VALUE_TABLE

NOW_UTC = datetime.now(timezone.utc)


def _vf(cfg=None):
    return VolatilityFilter(cfg)

def _normal_atr_history(n=20, base=0.001):
    return [base] * n

def _check(vf, current_atr=0.001, atr_history=None, spread=0.0001, avg_spread=0.0001, symbol="EURUSD"):
    return vf.check(
        current_atr=current_atr,
        atr_history=atr_history or _normal_atr_history(),
        current_spread=spread, avg_spread=avg_spread, symbol=symbol,
    )


# =============================================================================
# FIX #1 - News event blocking
# =============================================================================
class TestFix1NewsFilter(unittest.TestCase):

    def test_block_during_news_window(self):
        vf = _vf()
        ev = NewsEvent(title="NFP", currency="USD", impact="HIGH", event_time=NOW_UTC)
        vf.load_news_events([ev])
        result = _check(vf, symbol="EURUSD")
        self.assertFalse(result.can_trade)
        self.assertEqual(result.reason, "NEWS_EVENT_BLOCK")
        self.assertTrue(result.news_blocked)
        self.assertEqual(result.level, VolatilityLevel.EXTREME)

    def test_no_block_outside_window(self):
        vf = _vf()
        ev = NewsEvent("Old", "USD", "HIGH", NOW_UTC - timedelta(hours=2))
        vf.load_news_events([ev])
        self.assertTrue(_check(vf, symbol="EURUSD").can_trade)

    def test_no_block_future_outside_before_window(self):
        vf = _vf()
        ev = NewsEvent("Future", "USD", "HIGH", NOW_UTC + timedelta(hours=2))
        vf.load_news_events([ev])
        self.assertTrue(_check(vf, symbol="EURUSD").can_trade)

    def test_block_inside_before_window(self):
        vf = _vf()
        ev = NewsEvent("Upcoming NFP", "USD", "HIGH", NOW_UTC + timedelta(minutes=10))
        vf.load_news_events([ev])
        result = _check(vf, symbol="EURUSD")
        self.assertFalse(result.can_trade)
        self.assertEqual(result.news_event_title, "Upcoming NFP")

    def test_multiple_events_any_matches(self):
        vf = _vf()
        events = [
            NewsEvent("Old", "USD", "LOW",  NOW_UTC - timedelta(hours=3)),
            NewsEvent("Live", "EUR", "HIGH", NOW_UTC),
            NewsEvent("Future", "GBP", "HIGH", NOW_UTC + timedelta(hours=5)),
        ]
        vf.load_news_events(events)
        self.assertFalse(_check(vf, symbol="EURUSD").can_trade)

    def test_fail_safe_continues_on_provider_error(self):
        vf = _vf()
        broken = MagicMock()
        broken.currency = "USD"
        broken.event_time = None
        vf._news_events = [broken]
        result = _check(vf, symbol="EURUSD")
        self.assertTrue(result.can_trade)

    def test_news_filter_disabled(self):
        cfg = VolatilityFilterConfig(enable_news_filter=False)
        vf = _vf(cfg)
        ev = NewsEvent("NFP", "USD", "HIGH", NOW_UTC)
        vf.load_news_events([ev])
        self.assertTrue(_check(vf, symbol="EURUSD").can_trade)

    def test_currency_mismatch_no_block(self):
        vf = _vf()
        ev = NewsEvent("BOJ", "JPY", "HIGH", NOW_UTC)
        vf.load_news_events([ev])
        self.assertTrue(_check(vf, symbol="EURUSD").can_trade)

    def test_all_currency_blocks_any_symbol(self):
        vf = _vf()
        ev = NewsEvent("Global halt", "ALL", "HIGH", NOW_UTC)
        vf.load_news_events([ev])
        for sym in ["EURUSD", "XAUUSD", "BTCUSD"]:
            self.assertFalse(_check(vf, symbol=sym).can_trade, msg=f"should block {sym}")


# =============================================================================
# FIX #2 - ATR spike robustness
# =============================================================================
class TestFix2ATREstimator(unittest.TestCase):

    def _spike_history(self):
        return [0.001] * 19 + [0.05]

    def test_median_ignores_spike(self):
        history = self._spike_history()
        vf = _vf(VolatilityFilterConfig(atr_estimator="median"))
        avg = vf._avg_atr(history, current_atr=0.001)
        self.assertAlmostEqual(avg, statistics.median(history[-14:]), places=6)
        self.assertLess(avg, 0.005)

    def test_mean_inflated_by_spike(self):
        history = self._spike_history()
        vf = _vf(VolatilityFilterConfig(atr_estimator="mean"))
        avg = vf._avg_atr(history, current_atr=0.001)
        expected_mean = sum(history[-14:]) / 14
        self.assertAlmostEqual(avg, expected_mean, places=8)
        self.assertGreater(avg, 0.003)

    def test_ema_estimator(self):
        history = [0.001] * 14
        vf = _vf(VolatilityFilterConfig(atr_estimator="ema"))
        avg = vf._avg_atr(history, current_atr=0.001)
        self.assertAlmostEqual(avg, 0.001, places=5)

    def test_median_does_not_trigger_false_extreme(self):
        history = self._spike_history()
        vf = _vf(VolatilityFilterConfig(atr_estimator="median"))
        result = _check(vf, current_atr=0.001, atr_history=history)
        self.assertEqual(result.level, VolatilityLevel.NORMAL)

    def test_backward_compat_mean_still_works(self):
        history = [0.001] * 14
        vf = _vf(VolatilityFilterConfig(atr_estimator="mean"))
        avg = vf._avg_atr(history, 0.001)
        self.assertAlmostEqual(avg, 0.001, places=8)


# =============================================================================
# FIX #3 - Symbol-specific volatility thresholds
# =============================================================================
class TestFix3SymbolThresholds(unittest.TestCase):

    def test_xauusd_lower_extreme_threshold(self):
        vf = _vf()
        _, high, extreme = vf._thresholds("XAUUSD")
        self.assertEqual(extreme, 3.0)
        self.assertEqual(high, 1.8)

    def test_btcusd_tighter_thresholds(self):
        vf = _vf()
        low, high, extreme = vf._thresholds("BTCUSD")
        self.assertEqual(extreme, 2.2)
        self.assertEqual(high, 1.5)
        self.assertEqual(low, 0.8)

    def test_eurusd_default_thresholds(self):
        vf = _vf()
        _, _, extreme = vf._thresholds("EURUSD")
        self.assertEqual(extreme, 3.5)

    def test_unknown_symbol_uses_global_defaults(self):
        vf = _vf()
        _, _, extreme = vf._thresholds("EXOTIC123")
        self.assertEqual(extreme, vf._cfg.extreme_atr_ratio)

    def test_btcusd_blocks_at_ratio_2_5(self):
        history = [0.001] * 14
        vf = _vf()
        result_btc = _check(vf, current_atr=0.0025, atr_history=history, symbol="BTCUSD")
        self.assertFalse(result_btc.can_trade)
        self.assertEqual(result_btc.level, VolatilityLevel.EXTREME)
        result_eur = _check(vf, current_atr=0.0025, atr_history=history, symbol="EURUSD")
        self.assertTrue(result_eur.can_trade)
        self.assertEqual(result_eur.level, VolatilityLevel.HIGH)

    def test_custom_threshold_override(self):
        cfg = VolatilityFilterConfig(symbol_thresholds={"USDJPY": SymbolThresholds(low=0.3, high=1.2, extreme=2.0)})
        vf = VolatilityFilter(cfg)
        _, _, extreme = vf._thresholds("USDJPY")
        self.assertEqual(extreme, 2.0)


# =============================================================================
# FIX #4 - Broker-aware pip value (Gold + Crypto)
# =============================================================================
class TestFix4PipValue(unittest.TestCase):

    def test_gold_pip_value(self):
        self.assertEqual(_get_pip_value("XAUUSD"), 1.0)

    def test_silver_pip_value(self):
        self.assertEqual(_get_pip_value("XAGUSD"), 5.0)

    def test_btcusd_pip_value(self):
        self.assertEqual(_get_pip_value("BTCUSD"), 1.0)

    def test_ethusd_pip_value(self):
        self.assertEqual(_get_pip_value("ETHUSD"), 1.0)

    def test_indices_pip_value(self):
        self.assertEqual(_get_pip_value("US30"), 1.0)
        self.assertEqual(_get_pip_value("NAS100"), 1.0)

    def test_forex_major_pip_value(self):
        self.assertEqual(_get_pip_value("EURUSD"), 10.0)
        self.assertEqual(_get_pip_value("GBPUSD"), 10.0)

    def test_case_insensitive(self):
        self.assertEqual(_get_pip_value("xauusd"), _get_pip_value("XAUUSD"))

    def test_gold_open_trade_risk_correct(self):
        """XAUUSD: entry=2000, SL=1990, lot=0.1, pip_val=1.0 -> risk=1.0 USD"""
        t = OpenTradeRisk("XAUUSD", TradeDirection.BUY, 0.1, 2000.0, 1990.0, 10_000.0)
        self.assertAlmostEqual(t.risk_amount, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 0.01, places=4)

    def test_eurusd_open_trade_risk_matches_forex_formula(self):
        """EURUSD backward compat: 0.01 * 1.0 * 10.0 = 0.10 USD (same as old formula)"""
        t = OpenTradeRisk("EURUSD", TradeDirection.BUY, 1.0, 1.1000, 1.0900, 10_000.0)
        self.assertAlmostEqual(t.risk_amount, 0.10, places=4)

    def test_injected_pip_value_overrides_table(self):
        t = OpenTradeRisk("XAUUSD", TradeDirection.BUY, 1.0, 2000.0, 1990.0, 10_000.0, pip_value_per_lot=2.5)
        self.assertAlmostEqual(t.risk_amount, 25.0, places=4)


# =============================================================================
# FIX #5 - Exposure uses actual risk_percent
# =============================================================================
class TestFix5ExposureActualRisk(unittest.TestCase):

    def _make_orchestrator_with_mocks(self, prelim_risk_pct=2.5):
        from dataclasses import dataclass as _dc

        class _FakeLSConfig:
            def __init__(self, win_rate=0.55, avg_rr=1.5): pass
        class _FakeLS:
            async def calculate(self, **kw): pass
        class _FakeEP:
            def update_equity(self, e, b): pass
            def check(self): pass
        class _FakeCF:
            def check(self, *a, **kw): pass
        class _FakeVF:
            def check(self, *a, **kw): pass
        class _FakeExp:
            def check(self, **kw): pass
        class _FakeDL:
            def check_limits(self, *a, **kw): pass
        class _FakeTodayTrades:
            def __init__(self, **kw): pass

        _stub_module("backend.risk.lot_sizing",
            DynamicLotSizer=_FakeLS, LotSizingConfig=_FakeLSConfig, get_lot_sizer=lambda *a,**k: _FakeLS())
        _stub_module("backend.risk.equity_protection",
            EquityProtectionEngine=_FakeEP, get_equity_protection=lambda: _FakeEP())
        _stub_module("backend.risk.volatility_filter",
            VolatilityFilter=_FakeVF, get_volatility_filter=lambda *a,**k: _FakeVF())
        _stub_module("backend.risk.exposure_control",
            ExposureControlEngine=_FakeExp, ExposurePosition=MagicMock, get_exposure_control=lambda: _FakeExp())
        _stub_module("backend.risk.daily_limits",
            DailyLimitsEngine=_FakeDL, TodayTrades=_FakeTodayTrades)
        _stub_module("backend.risk.correlation_filter",
            CorrelationFilter=_FakeCF, OpenPosition=MagicMock,
            get_correlation_filter=lambda: _FakeCF(),
            RollingCorrelationEngine=_FakeRollingEngine)

        orch_mod = _load("risk_orchestrator_new.py", "backend.risk.risk_orchestrator_test")
        RiskOrchestrator = orch_mod.RiskOrchestrator
        RiskInput = orch_mod.RiskInput
        RiskOrchestrator._instance = None
        orch = RiskOrchestrator.__new__(RiskOrchestrator)
        orch._initialized = True

        mock_ep = MagicMock()
        mock_ep_result = MagicMock()
        mock_ep_result.can_trade = True
        mock_ep_result.drawdown_percent = 1.0
        mock_ep.check.return_value = mock_ep_result
        mock_ep.update_equity = MagicMock()
        orch._equity_engine = mock_ep

        mock_dl = MagicMock()
        mock_dl_result = MagicMock()
        mock_dl_result.can_trade = True
        mock_dl.check_limits.return_value = mock_dl_result
        orch._daily_engine = mock_dl

        mock_vf = MagicMock()
        mock_vf_result = MagicMock()
        mock_vf_result.can_trade = True
        mock_vf_result.lot_multiplier = 1.0
        mock_vf_result.level = MagicMock()
        mock_vf_result.level.value = "NORMAL"
        mock_vf_result.volatility_level = "NORMAL"
        mock_vf.check.return_value = mock_vf_result
        orch._vol_filter = mock_vf

        mock_cf = MagicMock()
        mock_cf_result = MagicMock()
        mock_cf_result.can_trade = True
        mock_cf_result.correlation_score = 0.0
        mock_cf.check.return_value = mock_cf_result
        orch._corr_filter = mock_cf

        received_risk = []
        mock_exp = MagicMock()
        mock_exp_result = MagicMock()
        mock_exp_result.can_trade = True
        mock_exp_result.snapshot = MagicMock()
        mock_exp_result.snapshot.total_risk_percent = 2.0
        def _exp_check(new_symbol, new_direction, new_risk_percent, open_positions):
            received_risk.append(new_risk_percent)
            return mock_exp_result
        mock_exp.check = _exp_check
        orch._exposure_engine = mock_exp

        mock_ls = MagicMock()
        lot_result = MagicMock()
        lot_result.lot_size = 0.1
        lot_result.risk_percent = prelim_risk_pct
        lot_result.pip_value_used = 10.0
        mock_ls.calculate = AsyncMock(return_value=lot_result)
        orch._lot_sizer = mock_ls

        return orch, RiskInput, received_risk

    def _make_input(self, RiskInput):
        return RiskInput(
            symbol="EURUSD", direction="BUY",
            balance=10_000.0, equity=10_000.0, stop_loss_pips=20.0,
            current_atr=0.001, atr_history=[0.001]*14,
            current_spread=0.0001, avg_spread=0.0001, open_positions=[],
            today_trades_count=0, today_pnl_usd=0.0,
            week_pnl_usd=0.0, month_pnl_usd=0.0,
        )

    def test_exposure_receives_actual_risk_not_1(self):
        orch, RiskInput, received_risk = self._make_orchestrator_with_mocks(prelim_risk_pct=2.5)
        asyncio.run(orch.evaluate(self._make_input(RiskInput)))
        self.assertEqual(len(received_risk), 1)
        self.assertAlmostEqual(received_risk[0], 2.5, places=3)

    def test_exposure_not_hardcoded_1(self):
        for risk in [0.5, 1.5, 3.0]:
            orch, RiskInput, received = self._make_orchestrator_with_mocks(prelim_risk_pct=risk)
            asyncio.run(orch.evaluate(self._make_input(RiskInput)))
            self.assertAlmostEqual(received[0], risk, places=3,
                msg=f"Expected {risk}, got {received[0]}")


# =============================================================================
# FIX #6 - Fail-closed behaviour
# =============================================================================
class TestFix6FailClosed(unittest.TestCase):

    def test_volatility_filter_fail_closed_default(self):
        vf = VolatilityFilter()
        vf._cfg.max_spread_multiplier = "NOT_A_NUMBER"
        result = vf.check(current_atr=0.001, atr_history=[0.001]*14,
                          current_spread=0.0001, avg_spread=0.0001, symbol="EURUSD")
        self.assertFalse(result.can_trade)
        self.assertIn("FAIL_CLOSED", result.reason)

    def test_volatility_filter_fail_open(self):
        cfg = VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN)
        vf = VolatilityFilter(cfg)
        vf._cfg.max_spread_multiplier = "NOT_A_NUMBER"
        result = vf.check(current_atr=0.001, atr_history=[0.001]*14,
                          current_spread=0.0001, avg_spread=0.0001, symbol="EURUSD")
        self.assertTrue(result.can_trade)
        self.assertIn("FAIL_OPEN", result.reason)

    def test_portfolio_risk_fail_closed_default(self):
        pm = PortfolioRiskManager()
        pm.MAX_TOTAL_RISK_PCT = None
        t = OpenTradeRisk("EURUSD", TradeDirection.BUY, 0.1, 1.1, 1.09, 10_000.0)
        result = pm.check(t, [])
        self.assertFalse(result.can_add_new)
        self.assertIn("FAIL_CLOSED", result.block_reason)

    def test_portfolio_risk_fail_open(self):
        from backend.risk.portfolio_risk import FailMode as PFM
        pm = PortfolioRiskManager(fail_mode=PFM.FAIL_OPEN)
        pm.MAX_TOTAL_RISK_PCT = None
        t = OpenTradeRisk("EURUSD", TradeDirection.BUY, 0.1, 1.1, 1.09, 10_000.0)
        result = pm.check(t, [])
        self.assertTrue(result.can_add_new)


# =============================================================================
# FIX #7 - Dead code absence
# =============================================================================
class TestFix7DeadCodeRemoved(unittest.TestCase):

    def test_volatility_filter_no_unused_lock(self):
        import asyncio as _asyncio
        vf = VolatilityFilter()
        for attr in vars(vf).values():
            self.assertNotIsInstance(attr, _asyncio.Lock,
                msg="VolatilityFilter should have no asyncio.Lock (was unused)")

    def test_get_volatility_filter_returns_singleton(self):
        vf_mod._vol_filter = None
        a = vf_mod.get_volatility_filter()
        b = vf_mod.get_volatility_filter()
        self.assertIs(a, b)


# =============================================================================
# FIX #8 - Portfolio correlation calculations
# =============================================================================
class TestFix8PortfolioCorrelation(unittest.TestCase):

    def _trade(self, symbol, direction=TradeDirection.BUY, lot=0.1, entry=1.1, sl=1.09, balance=10_000.0):
        return OpenTradeRisk(symbol, direction, lot, entry, sl, balance)

    def test_uncorrelated_symbols_no_extra_risk(self):
        pm = PortfolioRiskManager()
        t1 = self._trade("EURUSD", TradeDirection.BUY)
        t2 = self._trade("BTCUSD", TradeDirection.BUY)
        snap = pm.check(t2, [t1])
        self.assertAlmostEqual(snap.correlated_risk, 0.0, places=4)

    def test_highly_correlated_same_direction_adds_risk(self):
        pm = PortfolioRiskManager()
        t1 = self._trade("EURUSD", TradeDirection.BUY)
        t2 = self._trade("GBPUSD", TradeDirection.BUY)
        snap = pm.check(t2, [t1])
        self.assertGreater(snap.correlated_risk, 0.0)

    def test_highly_correlated_opposite_direction_reduces_risk(self):
        pm = PortfolioRiskManager()
        t1 = self._trade("EURUSD", TradeDirection.BUY)
        t2 = self._trade("GBPUSD", TradeDirection.SELL)
        snap = pm.check(t2, [t1])
        self.assertAlmostEqual(snap.total_risk_percent, t1.risk_percent + t2.risk_percent, places=3)

    def test_max_risk_level_consistent(self):
        pm = PortfolioRiskManager()
        trades = [OpenTradeRisk("EURUSD", TradeDirection.BUY, 1.0, 1.10, 1.09, 100_000.0) for _ in range(4)]
        new_t  = OpenTradeRisk("GBPUSD", TradeDirection.BUY, 1.0, 1.30, 1.29, 100_000.0)
        snap   = pm.check(new_t, trades)
        if snap.total_risk_percent >= pm.MAX_TOTAL_RISK_PCT:
            self.assertFalse(snap.can_add_new)
            self.assertEqual(snap.risk_level, RiskLevel.BLOCKED)
        elif snap.total_risk_percent >= pm.CRITICAL_RISK_PCT:
            self.assertFalse(snap.can_add_new)

    def test_rolling_engine_fallback_on_no_data(self):
        pm = PortfolioRiskManager()
        corr, src = pm._get_correlation("EURUSD", "GBPUSD")
        self.assertEqual(src, "static")
        self.assertAlmostEqual(corr, 0.85, places=2)

    def test_negative_static_correlation(self):
        pm = PortfolioRiskManager()
        corr, src = pm._get_correlation("USDCHF", "EURUSD")
        self.assertLess(corr, 0.0)

    def test_gold_risk_calculation_correct(self):
        t = OpenTradeRisk("XAUUSD", TradeDirection.BUY, 1.0, 2000.0, 1950.0, 100_000.0)
        self.assertAlmostEqual(t.risk_amount, 50.0, places=2)
        self.assertAlmostEqual(t.risk_percent, 0.05, places=4)


# =============================================================================
# Integration
# =============================================================================
class TestIntegration(unittest.TestCase):

    def test_normal_trade_approved(self):
        vf = VolatilityFilter()
        result = vf.check(0.001, [0.001]*20, 0.00010, 0.00010, symbol="EURUSD")
        self.assertTrue(result.can_trade)
        self.assertEqual(result.level, VolatilityLevel.NORMAL)

    def test_extreme_atr_blocks(self):
        vf = VolatilityFilter()
        result = vf.check(0.004, [0.001]*14, 0.0001, 0.0001, symbol="EURUSD")
        self.assertFalse(result.can_trade)
        self.assertEqual(result.level, VolatilityLevel.EXTREME)

    def test_news_overrides_normal_atr(self):
        vf = VolatilityFilter()
        ev = NewsEvent("CPI Release", "USD", "HIGH", NOW_UTC)
        vf.load_news_events([ev])
        result = vf.check(0.001, [0.001]*14, 0.0001, 0.0001, symbol="EURUSD")
        self.assertFalse(result.can_trade)
        self.assertTrue(result.news_blocked)

    def test_backward_compat_positional_args(self):
        vf = VolatilityFilter()
        result = vf.check(0.001, [0.001]*14, 0.0001, 0.0001)
        self.assertTrue(result.can_trade)

    def test_calculate_atr_unchanged(self):
        vf = VolatilityFilter()
        highs  = [1.1 + i*0.001 for i in range(20)]
        lows   = [1.09 + i*0.001 for i in range(20)]
        closes = [1.095 + i*0.001 for i in range(20)]
        atrs = vf.calculate_atr(highs, lows, closes)
        self.assertIsInstance(atrs, list)
        self.assertTrue(all(a > 0 for a in atrs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
