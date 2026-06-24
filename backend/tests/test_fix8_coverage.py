"""
backend/tests/test_fix8_coverage.py
====================================
FIX #8 - Test Coverage (>=90%) for all modified risk modules.

8 Topics:
  1. News event blocking          (PortfolioRiskManager)
  2. ATR spike robustness         (VolatilityFilter)
  3. Symbol-specific thresholds   (VolatilityFilter per asset class)
  4. Gold pip value               (lot_sizing + portfolio_risk)
  5. Crypto pip value             (lot_sizing + portfolio_risk)
  6. Exposure calculation         (ExposureControlEngine)
  7. Fail-closed behavior         (all 4 gates)
  8. Portfolio correlation calcs  (CorrelationFilter)

All values computed from production formulas:
  OpenTradeRisk.risk_amount  = abs(entry - sl) * lot * pip_val
  OpenTradeRisk.risk_percent = risk_amount / balance * 100
  LotSizer.raw_lot           = (balance * risk_pct/100) / (sl_pips * pip_val)
  ExposureControl.total      = sum(p.risk_percent for p in open_positions)
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import math
import sys
import types
import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Path helpers - load modules from /tmp/fix8_prod without backend package
# ---------------------------------------------------------------------------

def _load(name: str, path: str):
    """Load a module from an absolute file path, injecting stub backend pkg."""
    # Ensure backend.risk namespace exists
    if "backend" not in sys.modules:
        pkg = types.ModuleType("backend")
        pkg.__path__ = []
        sys.modules["backend"] = pkg
    if "backend.risk" not in sys.modules:
        pkg = types.ModuleType("backend.risk")
        pkg.__path__ = []
        sys.modules["backend.risk"] = pkg

    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


ROOT = "/tmp/fix8_prod"

_fm  = _load("backend.risk.fail_mode",       f"{ROOT}/fail_mode.py")
_vf  = _load("backend.risk.volatility_filter", f"{ROOT}/volatility_filter.py")
_cf  = _load("backend.risk.correlation_filter", f"{ROOT}/correlation_filter.py")
_ec  = _load("backend.risk.exposure_control",  f"{ROOT}/exposure_control.py")
_pr  = _load("backend.risk.portfolio_risk",    f"{ROOT}/portfolio_risk.py")
_ls  = _load("backend.risk.lot_sizing",        f"{ROOT}/lot_sizing.py")

# Canonical names
FailMode         = _fm.FailMode
coerce_fm        = _fm.coerce

VolatilityFilter = _vf.VolatilityFilter
VolatilityConfig = _vf.VolatilityConfig

CorrelationFilter       = _cf.CorrelationFilter
CorrelationFilterConfig = _cf.CorrelationFilterConfig

ExposureControlEngine = _ec.ExposureControlEngine
ExposureConfig        = _ec.ExposureConfig
ExposurePosition      = _ec.ExposurePosition

PortfolioRiskManager = _pr.PortfolioRiskManager
PortfolioRiskConfig  = _pr.PortfolioRiskConfig
OpenTradeRisk        = _pr.OpenTradeRisk
RiskLevel            = _pr.RiskLevel

LotSizer       = _ls.LotSizer
LotSizingConfig = _ls.LotSizingConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _otr(symbol="EURUSD", direction="BUY",
         lot=1.0, entry=11.0, sl=1.0, balance=10_000.0) -> "OpenTradeRisk":
    """
    Build OpenTradeRisk with precise risk calculation.
    Formula: risk_pct = abs(entry-sl) * lot * pip_val / balance * 100
    EURUSD pip_val=10.0:
      dist=10, lot=1 -> 10*1*10/10000*100 = 1.0%
      dist=21, lot=1 -> 21*1*10/10000*100 = 2.1%
    XAUUSD pip_val=1.0:
      dist=100, lot=1 -> 100*1*1/10000*100 = 1.0%
      dist=210, lot=1 -> 210*1*1/10000*100 = 2.1%
    """
    return OpenTradeRisk(
        symbol=symbol,
        direction=direction,
        lot_size=lot,
        entry_price=entry,
        stop_loss=sl,
        account_balance=balance,
    )


def _ep(symbol="EURUSD", direction="BUY", risk=1.0) -> "ExposurePosition":
    return ExposurePosition(symbol=symbol, direction=direction,
                            risk_percent=risk, risk_usd=risk * 100)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. NEWS EVENT BLOCKING
# ---------------------------------------------------------------------------

class TestNewsEventBlocking(unittest.TestCase):
    """
    Issue: PortfolioRiskManager had no try/except before FIX #6.
    Exception in check() -> propagate -> all limits bypassed.
    FIX: check() wraps _check_inner() + configurable fail_mode.
    """

    def setUp(self):
        self.cfg = PortfolioRiskConfig(
            max_portfolio_risk_pct=6.0,
            max_single_symbol_pct=2.0,
        )
        self.mgr = PortfolioRiskManager(config=self.cfg)

    def test_single_trade_too_large_blocked(self):
        """2.1% single trade > 2.0% limit -> SINGLE_TRADE_RISK blocked."""
        trade = _otr("EURUSD", "BUY", lot=1.0, entry=22.0, sl=1.0, balance=10_000)
        # dist=21, risk=21*1*10/10000*100=2.1%
        self.assertAlmostEqual(trade.risk_percent, 2.1, places=5)
        r = self.mgr.check(trade, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)
        self.assertEqual(r.risk_level, RiskLevel.BLOCKED)

    def test_single_trade_exactly_at_limit_allowed(self):
        """2.0% == limit: condition is STRICTLY >, so boundary is allowed."""
        trade = _otr("EURUSD", "BUY", lot=1.0, entry=21.0, sl=1.0, balance=10_000)
        # dist=20, risk=20*1*10/10000*100=2.0% NOT > 2.0% -> allowed
        self.assertAlmostEqual(trade.risk_percent, 2.0, places=5)
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)

    def test_portfolio_total_exceeded_blocked(self):
        """5 existing * 1.0% + 1.5% new = 6.5% > 6.0% -> PORTFOLIO_RISK blocked."""
        existing = [_otr("EURUSD", "BUY", lot=1.0, entry=11.0, sl=1.0)
                    for _ in range(5)]
        new_trade = _otr("GBPUSD", "SELL", lot=1.0, entry=16.0, sl=1.0)
        for t in existing:
            self.assertAlmostEqual(t.risk_percent, 1.0, places=5)
        self.assertAlmostEqual(new_trade.risk_percent, 1.5, places=5)
        r = self.mgr.check(new_trade, existing)
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_RISK", r.reason)

    def test_portfolio_remaining_cap_accurate(self):
        """remaining_cap = max(0, max_portfolio - existing_risk)."""
        existing = [_otr("EURUSD", "BUY", lot=1.0, entry=16.0, sl=1.0)
                    for _ in range(2)]
        new_trade = _otr("GBPUSD", "BUY", lot=1.0, entry=6.0, sl=1.0)
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.remaining_cap, 3.0, places=4)

    def test_risk_level_critical_when_near_limit(self):
        """total >= 80% of max (4.8%) -> CRITICAL."""
        existing = [_otr("EURUSD", "BUY", lot=1.0, entry=16.0, sl=1.0)
                    for _ in range(3)]
        new_trade = _otr("GBPUSD", "BUY", lot=1.0, entry=6.0, sl=1.0)
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.CRITICAL)

    def test_risk_level_warning(self):
        """total >= 60% of max (3.6%) -> WARNING."""
        existing = [_otr("EURUSD", "BUY", lot=1.0, entry=16.0, sl=1.0)
                    for _ in range(2)]
        new_trade = _otr("GBPUSD", "BUY", lot=1.0, entry=10.0, sl=1.0)
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.WARNING)

    def test_risk_level_safe(self):
        """total < 3.6% -> SAFE."""
        new_trade = _otr("EURUSD", "BUY", lot=1.0, entry=6.0, sl=1.0)
        r = self.mgr.check(new_trade, [])
        self.assertTrue(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.SAFE)

    def test_fail_closed_exception_blocks(self):
        """Exception in check() + FAIL_CLOSED -> blocked."""
        mgr = PortfolioRiskManager(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("crash")):
            trade = _otr()
            r = mgr.check(trade, [])
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_CHECK_ERROR", r.reason)

    def test_fail_open_exception_allows(self):
        """Exception in check() + FAIL_OPEN -> allowed."""
        mgr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("crash")):
            with self.assertLogs("risk.portfolio_risk", level="CRITICAL"):
                r = mgr.check(_otr(), [])
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_async_check_same_result(self):
        """check_async() without lot_sizer -> same result as check()."""
        mgr   = PortfolioRiskManager()
        trade  = _otr("EURUSD", "BUY", lot=1.0, entry=22.0, sl=1.0)
        trade2 = _otr("EURUSD", "BUY", lot=1.0, entry=22.0, sl=1.0)
        sync_r  = mgr.check(trade, [])
        async_r = _run(mgr.check_async(trade2, []))
        self.assertEqual(sync_r.can_trade, async_r.can_trade)
        self.assertEqual(sync_r.reason,    async_r.reason)


# ---------------------------------------------------------------------------
# 2. ATR SPIKE ROBUSTNESS
# ---------------------------------------------------------------------------

class TestATRSpikeRobustness(unittest.TestCase):
    """
    Issue: VolatilityFilter.check() had no try/except before FIX #6.
    avg_atr=0 -> ZeroDivisionError -> propagate -> gate crashed -> trade allowed.
    FIX: check() wraps _check_inner(); FAIL_CLOSED/FAIL_OPEN applied.
    Production thresholds (VolatilityConfig defaults):
      atr_min_ratio=0.5  (condition: atr_ratio < min -> ATR_TOO_LOW)
      atr_max_ratio=3.0  (condition: atr_ratio > max -> ATR_TOO_HIGH)  -- strictly >
      max_spread_ratio=2.0
      min_atr_bars=5
    """

    def setUp(self):
        self.cfg = VolatilityConfig(
            atr_min_ratio=0.5,
            atr_max_ratio=3.0,
            max_spread_ratio=2.0,
            min_atr_bars=5,
        )
        self.vf      = VolatilityFilter(config=self.cfg)
        self.history = [0.001] * 10

    def test_normal_conditions_allowed(self):
        r = self.vf.check(0.001, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "VOLATILITY_OK")
        self.assertAlmostEqual(r.atr_ratio, 1.0, places=5)

    def test_atr_spike_blocked(self):
        """ratio=4.0 > 3.0 -> ATR_TOO_HIGH -> blocked."""
        r = self.vf.check(0.004, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)
        self.assertAlmostEqual(r.atr_ratio, 4.0, places=5)

    def test_atr_spike_boundary_allowed(self):
        """ratio=3.0 exactly at max: condition is STRICTLY > -> allowed."""
        r = self.vf.check(0.003, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.atr_ratio, 3.0, places=5)

    def test_atr_low_blocked(self):
        """ratio=0.4 < 0.5 -> ATR_TOO_LOW -> blocked."""
        r = self.vf.check(0.0004, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_LOW", r.reason)

    def test_atr_low_boundary_allowed(self):
        """ratio=0.5 exactly at min: condition is STRICTLY < -> allowed."""
        r = self.vf.check(0.0005, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.atr_ratio, 0.5, places=5)

    def test_spread_too_wide_blocked(self):
        """spread_ratio=3.0 > 2.0 -> SPREAD_TOO_WIDE -> blocked."""
        r = self.vf.check(0.001, self.history, 0.0006, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_WIDE", r.reason)
        self.assertAlmostEqual(r.spread_ratio, 3.0, places=5)

    def test_insufficient_history_allowed(self):
        """< min_atr_bars bars -> INSUFFICIENT_ATR_HISTORY -> allowed."""
        r = self.vf.check(0.001, [0.001, 0.001], 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "INSUFFICIENT_ATR_HISTORY")

    def test_zero_avg_atr_allowed(self):
        """avg_atr=0 -> ZERO_AVG_ATR -> allowed (safe fallback)."""
        r = self.vf.check(0.001, [0.0] * 10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "ZERO_AVG_ATR")

    def test_fail_closed_exception_blocks(self):
        """Exception inside _check_inner + FAIL_CLOSED -> blocked."""
        vf = VolatilityFilter(VolatilityConfig())
        with patch.object(vf, "_check_inner", side_effect=ZeroDivisionError("boom")):
            with self.assertLogs("risk.volatility_filter", level="ERROR"):
                r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)
        self.assertIn("ZeroDivisionError", r.reason)

    def test_fail_open_exception_allows(self):
        """Exception inside _check_inner + FAIL_OPEN -> allowed + CRITICAL log."""
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=ValueError("bad")):
            with self.assertLogs("risk.volatility_filter", level="CRITICAL"):
                r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "BTCUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_cache_populated_on_success(self):
        """Successful check populates cache for symbol."""
        self.vf.check(0.001, self.history, 0.0002, 0.0002, "EURUSD")
        cached = self.vf.get_cached("EURUSD")
        self.assertIsNotNone(cached)
        result, ts = cached
        self.assertTrue(result.can_trade)


# ---------------------------------------------------------------------------
# 3. SYMBOL-SPECIFIC THRESHOLDS
# ---------------------------------------------------------------------------

class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    Issue: One global VolatilityConfig for all assets is wrong.
    BTC has normal ATR ratio of 8-10x; Gold is tighter at 2x.
    FIX: Construct per-asset VolatilityFilter with appropriate thresholds.
    """

    def test_gold_tight_threshold(self):
        """Gold: atr_max_ratio=2.0 (tighter). ratio=2.33 > 2.0 -> blocked."""
        vf      = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        history = [3.0] * 10
        r = vf.check(7.0, history, 0.5, 0.5, "XAUUSD")  # ratio=7/3=2.33
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_gold_normal_allowed(self):
        """Gold: ratio=1.5 < 2.0 -> allowed."""
        vf      = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        history = [3.0] * 10
        r = vf.check(4.5, history, 0.5, 0.5, "XAUUSD")  # ratio=1.5
        self.assertTrue(r.can_trade)

    def test_btc_loose_threshold(self):
        """BTC: atr_max_ratio=10.0 (looser). ratio=8.0 < 10.0 -> allowed."""
        vf      = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        history = [1000.0] * 10
        r = vf.check(8000.0, history, 50.0, 50.0, "BTCUSD")  # ratio=8.0
        self.assertTrue(r.can_trade)

    def test_btc_extreme_blocked(self):
        """BTC: ratio=12.0 > 10.0 -> ATR_TOO_HIGH."""
        vf      = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        history = [1000.0] * 10
        r = vf.check(12000.0, history, 50.0, 50.0, "BTCUSD")  # ratio=12.0
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_cache_isolation_between_symbols(self):
        """EURUSD spike does NOT affect GBPUSD cache."""
        vf = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        h  = [0.001] * 10
        vf.check(0.004, h, 0.0002, 0.0002, "EURUSD")  # blocked
        r = vf.check(0.001, h, 0.0002, 0.0002, "GBPUSD")
        self.assertTrue(r.can_trade)

    def test_forex_global_threshold(self):
        """Default atr_max_ratio=3.0; EURUSD ratio=2.5 -> allowed."""
        vf = VolatilityFilter()
        h  = [0.001] * 10
        r  = vf.check(0.0025, h, 0.0002, 0.0002, "EURUSD")  # ratio=2.5
        self.assertTrue(r.can_trade)

    def test_different_configs_produce_different_results(self):
        """Same ATR, different threshold configs -> different outcomes."""
        h = [1.0] * 10
        vf_tight = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        vf_loose = VolatilityFilter(VolatilityConfig(atr_max_ratio=5.0, min_atr_bars=5))
        r_tight = vf_tight.check(3.0, h, 0.5, 0.5, "XAUUSD")  # ratio=3.0 > 2.0
        r_loose = vf_loose.check(3.0, h, 0.5, 0.5, "XAUUSD")  # ratio=3.0 < 5.0
        self.assertFalse(r_tight.can_trade)
        self.assertTrue(r_loose.can_trade)


# ---------------------------------------------------------------------------
# 4. GOLD PIP VALUE
# ---------------------------------------------------------------------------

class TestGoldPipValue(unittest.TestCase):
    """
    Issue (FIX #4): XAUUSD pip_value = 10.0 in BOTH modules -> 10x wrong.
    Correct: Gold pip = $0.01/oz * 100oz lot = $1.00
    With pip_val=10: lot_sizer 10x undersized -> actual risk 10% of intended.
    FIX: Both tables now XAUUSD = 1.0.
    """

    def test_lot_sizing_table_gold(self):
        self.assertEqual(_ls._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_portfolio_risk_table_gold(self):
        self.assertEqual(_pr._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_lot_sizer_resolve_xauusd(self):
        self.assertEqual(_ls._resolve_pip_value("XAUUSD"), 1.0)

    def test_lot_sizer_resolve_gold_alias(self):
        self.assertEqual(_ls._resolve_pip_value("GOLD"), 1.0)

    def test_lot_sizer_resolve_xauusd_suffix(self):
        self.assertEqual(_ls._resolve_pip_value("XAUUSDm"), 1.0)

    def test_portfolio_risk_get_pip_value_gold(self):
        self.assertEqual(_pr._get_pip_value("XAUUSD"), 1.0)

    def test_portfolio_risk_get_pip_value_gold_alias(self):
        self.assertEqual(_pr._get_pip_value("GOLD"), 1.0)

    def test_silver_pip_value_lot_sizing(self):
        self.assertEqual(_ls._PIP_VALUE_TABLE["XAGUSD"], 50.0)

    def test_silver_pip_value_portfolio_risk(self):
        self.assertEqual(_pr._PIP_VALUE_TABLE["XAGUSD"], 50.0)

    def test_open_trade_risk_gold_formula(self):
        """
        XAUUSD risk formula:
          dist=210, lot=1, pip_val=1.0, balance=10000
          risk_amount = 210 * 1 * 1.0 = 210
          risk_percent = 210 / 10000 * 100 = 2.1%
        """
        trade = _otr("XAUUSD", "BUY", lot=1.0, entry=211.0, sl=1.0)
        self.assertAlmostEqual(trade.risk_percent, 2.1, places=5)
        self.assertAlmostEqual(trade.risk_amount,  210.0, places=5)

    def test_gold_not_ten_times_wrong(self):
        """Regression: old value was 10.0 -> 10x inflated risk."""
        trade = _otr("XAUUSD", "BUY", lot=1.0, entry=211.0, sl=1.0)
        self.assertAlmostEqual(trade.risk_percent, 2.1, places=5)
        self.assertNotAlmostEqual(trade.risk_percent, 21.0, places=1)

    def test_lot_sizer_gold_calculation(self):
        """
        LotSizer(XAUUSD, balance=10000, sl=50pips, risk=1%):
          risk_usd = 10000 * 0.01 = 100
          raw_lot  = 100 / (50 * 1.0) = 2.0  -> lot = 2.0
        """
        sizer = LotSizer(LotSizingConfig(risk_percent=1.0, min_lot=0.01, max_lot=5.0))
        result = _run(sizer.calculate("XAUUSD", 10000, 50))
        self.assertAlmostEqual(result.lot_size, 2.0, places=2)

    def test_lot_sizer_gold_pip_value_method(self):
        self.assertEqual(LotSizer().get_pip_value("XAUUSD"), 1.0)


# ---------------------------------------------------------------------------
# 5. CRYPTO PIP VALUE
# ---------------------------------------------------------------------------

class TestCryptoPipValue(unittest.TestCase):
    """
    Issue (FIX #4): ETHUSD pip_value wrong -> lot 100x oversized -> account blow.
    FIX: All crypto pip_value = 1.0 in both modules.
    """

    CRYPTO_SYMBOLS = ["BTCUSD", "ETHUSD", "LTCUSD", "BNBUSD", "XRPUSD"]

    def test_lot_sizing_table_all_crypto(self):
        for sym in self.CRYPTO_SYMBOLS:
            with self.subTest(sym=sym):
                self.assertEqual(_ls._PIP_VALUE_TABLE[sym], 1.0)

    def test_portfolio_risk_table_btc_eth(self):
        for sym in ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"]:
            with self.subTest(sym=sym):
                self.assertEqual(_pr._PIP_VALUE_TABLE[sym], 1.0)

    def test_lot_sizer_resolve_btc(self):
        self.assertEqual(_ls._resolve_pip_value("BTCUSD"), 1.0)

    def test_lot_sizer_resolve_eth(self):
        self.assertEqual(_ls._resolve_pip_value("ETHUSD"), 1.0)

    def test_lot_sizer_resolve_btc_alias(self):
        self.assertEqual(_ls._resolve_pip_value("BTC"), 1.0)

    def test_lot_sizer_resolve_bitcoin_alias(self):
        self.assertEqual(_ls._resolve_pip_value("BITCOIN"), 1.0)

    def test_lot_sizer_resolve_eth_alias(self):
        self.assertEqual(_ls._resolve_pip_value("ETH"), 1.0)

    def test_lot_sizer_resolve_btcusd_suffix(self):
        self.assertEqual(_ls._resolve_pip_value("BTCUSDm"), 1.0)

    def test_open_trade_risk_btc_formula(self):
        """
        BTCUSD risk formula (pip_val=1.0):
          dist=500, lot=1, balance=10000
          risk_amount = 500 * 1 * 1.0 = 500
          risk_percent = 500 / 10000 * 100 = 5.0%
        """
        trade = _otr("BTCUSD", "BUY", lot=1.0, entry=501.0, sl=1.0)
        self.assertAlmostEqual(trade.risk_percent, 5.0, places=5)

    def test_lot_sizer_btc_calculation(self):
        """
        LotSizer(BTCUSD, balance=10000, sl=500pips, risk=1%):
          risk_usd = 100; raw_lot = 100/(500*1.0)=0.2 -> lot=0.20
        """
        sizer = LotSizer(LotSizingConfig(risk_percent=1.0, min_lot=0.01, max_lot=5.0))
        result = _run(sizer.calculate("BTCUSD", 10000, 500))
        self.assertAlmostEqual(result.lot_size, 0.20, places=2)

    def test_lot_sizer_eth_pip_value(self):
        self.assertEqual(LotSizer().get_pip_value("ETHUSD"), 1.0)

    def test_crypto_not_wrong_legacy_value(self):
        """Regression: old ETHUSD = 0.01 (100x too small)."""
        self.assertNotEqual(_ls._resolve_pip_value("ETHUSD"), 0.01)
        self.assertEqual(_ls._resolve_pip_value("ETHUSD"), 1.0)


# ---------------------------------------------------------------------------
# 6. EXPOSURE CALCULATION
# ---------------------------------------------------------------------------

class TestExposureCalculation(unittest.TestCase):
    """
    Issue: ExposureControlEngine.check() had no try/except before FIX #6.
    Any AttributeError from corrupt ExposurePosition -> propagate -> unlimited exposure.
    FIX: check() wraps _check_inner() + get_snapshot() try/except.
    Production limits (ExposureConfig defaults):
      max_total_risk_percent = 5.0
      max_risk_per_symbol    = 2.0
      max_open_trades        = 5
    """

    def setUp(self):
        self.cfg    = ExposureConfig(
            max_total_risk_percent=5.0,
            max_risk_per_symbol=2.0,
            max_open_trades=5,
        )
        self.engine = ExposureControlEngine(config=self.cfg)

    def test_allowed_under_all_limits(self):
        ops = [_ep("EURUSD", risk=1.0)]
        r = self.engine.check("GBPUSD", "BUY", 1.0, ops, 10_000)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.projected_total_risk, 2.0, places=5)

    def test_total_risk_exceeded_blocked(self):
        """4 * 1.0% + 1.5% = 5.5% > 5.0% -> blocked."""
        ops = [_ep("EURUSD", risk=1.0)] * 4
        r = self.engine.check("GBPUSD", "BUY", 1.5, ops, 10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("TOTAL", r.reason)

    def test_total_risk_boundary_allowed(self):
        """4 * 1.0% + 1.0% = 5.0% NOT > 5.0% -> allowed (strictly >)."""
        ops = [_ep("EURUSD", risk=1.0)] * 4
        r = self.engine.check("GBPUSD", "BUY", 1.0, ops, 10_000)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.projected_total_risk, 5.0, places=5)

    def test_symbol_risk_exceeded_blocked(self):
        """EURUSD 1.5% + new 1.0% = 2.5% > 2.0% -> blocked."""
        ops = [_ep("EURUSD", risk=1.5)]
        r = self.engine.check("EURUSD", "SELL", 1.0, ops, 10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("SYMBOL", r.reason)

    def test_symbol_risk_boundary_allowed(self):
        """EURUSD 1.0% + new 1.0% = 2.0% NOT > 2.0% -> allowed."""
        ops = [_ep("EURUSD", risk=1.0)]
        r = self.engine.check("EURUSD", "BUY", 1.0, ops, 10_000)
        self.assertTrue(r.can_trade)

    def test_max_open_trades_blocked(self):
        """5 existing = max_open_trades -> blocked."""
        ops = [_ep(f"SYM{i}", risk=0.5) for i in range(5)]
        r = self.engine.check("EURUSD", "BUY", 0.5, ops, 10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("TRADE", r.reason)

    def test_projected_total_risk_accurate(self):
        """projected_total = current_total + new_risk."""
        ops = [_ep("EURUSD", risk=2.0), _ep("GBPUSD", risk=1.5)]
        r = self.engine.check("AUDUSD", "BUY", 0.5, ops, 10_000)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.projected_total_risk, 4.0, places=5)

    def test_empty_positions_allowed(self):
        r = self.engine.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertTrue(r.can_trade)

    def test_fail_closed_exception_blocks(self):
        engine = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(engine, "_check_inner", side_effect=AttributeError("corrupt")):
            r = engine.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_exception_allows(self):
        engine = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(engine, "_check_inner", side_effect=RuntimeError("oops")):
            with self.assertLogs("risk.exposure_control", level="CRITICAL"):
                r = engine.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_get_snapshot_fail_closed_reraises(self):
        engine = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(engine, "_snapshot_inner", side_effect=RuntimeError("snap")):
            with self.assertRaises(RuntimeError):
                engine.get_snapshot([])

    def test_get_snapshot_fail_open_empty(self):
        engine = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(engine, "_snapshot_inner", side_effect=RuntimeError("snap")):
            snap = engine.get_snapshot([])
        self.assertEqual(snap.total_risk_percent, 0.0)
        self.assertFalse(snap.limit_breached)

    def test_snapshot_accurate_with_positions(self):
        ops  = [_ep("EURUSD", risk=1.5), _ep("GBPUSD", risk=2.0)]
        snap = self.engine.get_snapshot(ops)
        self.assertAlmostEqual(snap.total_risk_percent, 3.5, places=5)
        self.assertEqual(snap.open_trade_count, 2)
        self.assertIn("EURUSD", snap.risk_by_symbol)
        self.assertIn("GBPUSD", snap.risk_by_symbol)


# ---------------------------------------------------------------------------
# 7. FAIL-CLOSED BEHAVIOUR
# ---------------------------------------------------------------------------

class TestFailClosedBehaviour(unittest.TestCase):
    """
    Issue: Before FIX #6:
      CorrelationFilter: except: allow_trade=True  <- SILENT (no log!)
      ExposureControl:   no try/except at all
      VolatilityFilter:  no try/except at all
      PortfolioRisk:     no try/except at all
    FIX: All gates:
      - configurable FailMode (FAIL_CLOSED / FAIL_OPEN)
      - default = FAIL_CLOSED
      - every exception logged
      - single source of truth: all import from fail_mode.py
    """

    def test_fail_mode_enum_values(self):
        self.assertEqual(FailMode.FAIL_CLOSED, "FAIL_CLOSED")
        self.assertEqual(FailMode.FAIL_OPEN,   "FAIL_OPEN")

    def test_coerce_string_uppercase(self):
        self.assertIs(coerce_fm("FAIL_CLOSED"), FailMode.FAIL_CLOSED)
        self.assertIs(coerce_fm("FAIL_OPEN"),   FailMode.FAIL_OPEN)

    def test_coerce_string_lowercase(self):
        self.assertIs(coerce_fm("fail_closed"), FailMode.FAIL_CLOSED)
        self.assertIs(coerce_fm("fail_open"),   FailMode.FAIL_OPEN)

    def test_coerce_passthrough(self):
        self.assertIs(coerce_fm(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)

    def test_sot_volatility_filter(self):
        self.assertIs(_vf.FailMode, _fm.FailMode)

    def test_sot_correlation_filter(self):
        self.assertIs(_cf.FailMode, _fm.FailMode)

    def test_sot_exposure_control(self):
        self.assertIs(_ec.FailMode, _fm.FailMode)

    def test_sot_portfolio_risk(self):
        self.assertIs(_pr.FailMode, _fm.FailMode)

    def test_default_volatility_filter(self):
        self.assertIs(VolatilityFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_default_exposure_control(self):
        self.assertIs(ExposureControlEngine()._fail_mode, FailMode.FAIL_CLOSED)

    def test_default_correlation_filter(self):
        self.assertIs(CorrelationFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_default_portfolio_risk(self):
        self.assertIs(PortfolioRiskManager()._fail_mode, FailMode.FAIL_CLOSED)

    def test_string_coerce_in_constructor(self):
        ec = ExposureControlEngine(fail_mode="fail_open")
        self.assertIs(ec._fail_mode, FailMode.FAIL_OPEN)

    def test_vf_exception_logged_fail_closed(self):
        vf = VolatilityFilter()
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("x")):
            with self.assertLogs("risk.volatility_filter", level="ERROR") as cm:
                vf.check(1.0, [1.0]*10, 0.1, 0.1, "EURUSD")
        self.assertTrue(any("fail_mode" in m for m in cm.output))

    def test_vf_exception_logged_fail_open(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=RuntimeError("x")):
            with self.assertLogs("risk.volatility_filter", level="CRITICAL") as cm:
                vf.check(1.0, [1.0]*10, 0.1, 0.1, "EURUSD")
        self.assertTrue(any("FAIL_OPEN" in m for m in cm.output))

    def test_ec_exception_logged_fail_closed(self):
        ec = ExposureControlEngine()
        with patch.object(ec, "_check_inner", side_effect=AttributeError("boom")):
            with self.assertLogs("risk.exposure_control", level="ERROR"):
                ec.check("EURUSD", "BUY", 1.0, [], 10_000)

    def test_ec_exception_logged_fail_open(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, "_check_inner", side_effect=AttributeError("boom")):
            with self.assertLogs("risk.exposure_control", level="CRITICAL") as cm:
                ec.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertTrue(any("FAIL_OPEN" in m or "swallowed" in m for m in cm.output))

    def test_pr_exception_logged_fail_closed(self):
        pr = PortfolioRiskManager()
        with patch.object(pr, "_check_inner", side_effect=RuntimeError("err")):
            with self.assertLogs("risk.portfolio_risk", level="ERROR"):
                pr.check(_otr(), [])

    def test_cf_exception_fail_closed_async(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("boom")):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = _run(cf.check("EURUSD", "BUY", []))
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_cf_exception_fail_open_async(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("boom")):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = _run(cf.check("EURUSD", "BUY", []))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)


# ---------------------------------------------------------------------------
# 8. PORTFOLIO CORRELATION CALCULATIONS
# ---------------------------------------------------------------------------

class TestPortfolioCorrelationCalcs(unittest.TestCase):
    """
    Issue: Before FIX #6: CorrelationFilter.check() had no outer try/except.
    Per-pair exception -> corr=0.0 (inner catch OK) but outer exception
    -> propagate -> fail_mode gate completely bypassed.
    Production threshold: max_corr=0.85, condition abs(corr) >= 0.85.
    """

    def _make_engine(self, corr_map: dict):
        engine = MagicMock()

        async def get_corr(a, b):
            key = (a, b) if (a, b) in corr_map else (b, a)
            return corr_map.get(key, 0.0)

        engine.get_correlation = get_corr
        return engine

    def _make_cf(self, corr_map, fail_mode=FailMode.FAIL_CLOSED, max_corr=0.85):
        engine = self._make_engine(corr_map)
        cfg    = CorrelationFilterConfig(max_corr=max_corr)
        return CorrelationFilter(config=cfg, correlation_engine=engine,
                                 fail_mode=fail_mode)

    def test_no_positions_allowed(self):
        cf = CorrelationFilter()
        r  = _run(cf.check("EURUSD", "BUY", []))
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "NO_POSITIONS_OR_ENGINE")

    def test_no_engine_allowed(self):
        cf = CorrelationFilter(correlation_engine=None)
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_high_positive_correlation_blocked(self):
        """corr=0.92 >= 0.85 -> CORR_TOO_HIGH."""
        cf = self._make_cf({("EURUSD", "GBPUSD"): 0.92})
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("CORR_TOO_HIGH", r.reason)
        self.assertAlmostEqual(abs(r.correlation), 0.92, places=5)
        self.assertEqual(r.pair_checked, "GBPUSD")

    def test_high_negative_correlation_blocked(self):
        """abs(-0.92)=0.92 >= 0.85 -> CORR_TOO_HIGH."""
        cf = self._make_cf({("EURUSD", "USDCHF"): -0.92})
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "USDCHF"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("CORR_TOO_HIGH", r.reason)

    def test_correlation_at_boundary_blocked(self):
        """corr=0.85 exactly: abs(0.85) >= 0.85 -> blocked (inclusive)."""
        cf = self._make_cf({("EURUSD", "GBPUSD"): 0.85})
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertFalse(r.can_trade)

    def test_correlation_just_below_boundary_allowed(self):
        """corr=0.84 < 0.85 -> allowed."""
        cf = self._make_cf({("EURUSD", "GBPUSD"): 0.84})
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_low_correlation_allowed(self):
        cf = self._make_cf({("EURUSD", "GBPUSD"): 0.30})
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_same_symbol_skipped(self):
        """Position with same symbol -> skipped (engine not called)."""
        call_log = []

        async def get_corr(a, b):
            call_log.append((a, b))
            return 0.99

        engine = MagicMock()
        engine.get_correlation = get_corr
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(),
            correlation_engine=engine,
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "EURUSD"}]))
        self.assertTrue(r.can_trade)
        self.assertEqual(len(call_log), 0)

    def test_per_pair_exception_uses_zero_correlation(self):
        """Inner per-pair engine crash -> corr=0.0 -> allowed (inner catch)."""
        async def get_corr(a, b):
            raise RuntimeError("engine down")

        engine = MagicMock()
        engine.get_correlation = get_corr
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(),
            correlation_engine=engine,
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_early_exit_on_first_breach(self):
        """First blocking pair -> early return; second pair NOT checked."""
        call_log = []

        async def get_corr(a, b):
            call_log.append((a, b))
            if b == "GBPUSD":
                return 0.92
            return 0.30

        engine = MagicMock()
        engine.get_correlation = get_corr
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=engine,
        )
        positions = [{"symbol": "GBPUSD"}, {"symbol": "AUDUSD"}]
        r = _run(cf.check("EURUSD", "BUY", positions))
        self.assertFalse(r.can_trade)
        self.assertEqual(len(call_log), 1)
        self.assertIn("GBPUSD", str(call_log[0]))

    def test_outer_exception_fail_closed_blocks(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("outer crash")):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_outer_exception_fail_open_allows(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("outer crash")):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_multiple_positions_all_below_threshold(self):
        cf = self._make_cf({
            ("EURUSD", "AUDUSD"): 0.50,
            ("EURUSD", "NZDUSD"): 0.60,
        })
        positions = [{"symbol": s} for s in ["AUDUSD", "NZDUSD"]]
        r = _run(cf.check("EURUSD", "BUY", positions))
        self.assertTrue(r.can_trade)

    def test_pair_checked_field_populated(self):
        cf = self._make_cf({("EURUSD", "GBPUSD"): 0.92})
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertEqual(r.pair_checked, "GBPUSD")


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration(unittest.TestCase):
    """Cross-gate regression guards."""

    def test_gold_pip_consistent_across_modules(self):
        self.assertEqual(_ls._PIP_VALUE_TABLE.get("XAUUSD"), 1.0)
        self.assertEqual(_pr._PIP_VALUE_TABLE.get("XAUUSD"), 1.0)

    def test_all_gates_default_fail_closed(self):
        gates = [
            VolatilityFilter()._fail_mode,
            ExposureControlEngine()._fail_mode,
            CorrelationFilter()._fail_mode,
            PortfolioRiskManager()._fail_mode,
        ]
        for fm in gates:
            self.assertIs(fm, FailMode.FAIL_CLOSED)

    def test_failmode_single_source_of_truth(self):
        self.assertIs(_vf.FailMode, _fm.FailMode)
        self.assertIs(_cf.FailMode, _fm.FailMode)
        self.assertIs(_ec.FailMode, _fm.FailMode)
        self.assertIs(_pr.FailMode, _fm.FailMode)

    def test_exposure_receives_real_risk_not_hardcoded(self):
        """FIX #5 regression: real new_risk_percent passed, NOT hardcoded 1.0."""
        engine = ExposureControlEngine(ExposureConfig(
            max_total_risk_percent=10.0,
            max_risk_per_symbol=10.0,
            max_open_trades=10,
        ))
        r = engine.check("GBPUSD", "BUY", 3.0, [], 10_000)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.projected_total_risk, 3.0, places=5)

    def test_portfolio_and_exposure_share_failmode_enum(self):
        pr_fm = _pr.FailMode
        ec_fm = _ec.FailMode
        self.assertIs(pr_fm, ec_fm)


if __name__ == "__main__":
    unittest.main(verbosity=2)
