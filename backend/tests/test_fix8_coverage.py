"""
test_fix8_coverage.py
=====================
FIX #8 -- Test Coverage for 8 topics.
All tests load production files directly from /tmp/prod_*.py
using importlib so no backend package installation required.

Topics:
  1.  News event blocking         (PortfolioRiskManager gates)
  2.  ATR spike robustness        (VolatilityFilter thresholds + fail-mode)
  3.  Symbol-specific thresholds  (per-asset VolatilityConfig)
  4.  Gold pip value              (lot_sizing + portfolio_risk = 1.0)
  5.  Crypto pip value            (BTCUSD/ETHUSD/... = 1.0)
  6.  Exposure calculation        (3 limits + fail-mode)
  7.  Fail-closed behavior        (SSoT + all 4 gates default FAIL_CLOSED)
  8.  Portfolio correlation       (CORR_TOO_HIGH + same-symbol + fail-mode)
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

# -- asyncio helper: always creates a fresh loop -------------------------------
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# -- module loader -------------------------------------------------------------
def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_BASE = Path("/tmp")

# -- load canonical FailMode FIRST -- all modules will import THIS object -------
_fm_mod = _load("backend.risk.fail_mode",         str(_BASE / "prod_fail_mode.py"))
FailMode = _fm_mod.FailMode
coerce   = _fm_mod.coerce

# -- load in dependency order --------------------------------------------------
_ls_mod  = _load("backend.risk.lot_sizing",        str(_BASE / "prod_lot_sizing.py"))
_pr_mod  = _load("backend.risk.portfolio_risk",    str(_BASE / "prod_portfolio_risk.py"))
_vf_mod  = _load("backend.risk.volatility_filter", str(_BASE / "prod_volatility_filter.py"))
_cf_mod  = _load("backend.risk.correlation_filter",str(_BASE / "prod_correlation_filter.py"))
_ec_mod  = _load("backend.risk.exposure_control",  str(_BASE / "prod_exposure_control.py"))

# -- aliases -------------------------------------------------------------------
VolatilityFilter        = _vf_mod.VolatilityFilter
VolatilityConfig        = _vf_mod.VolatilityConfig
VolatilityCheckResult   = _vf_mod.VolatilityCheckResult

CorrelationFilter       = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig

ExposureControlEngine   = _ec_mod.ExposureControlEngine
ExposureConfig          = _ec_mod.ExposureConfig
ExposurePosition        = _ec_mod.ExposurePosition

PortfolioRiskManager    = _pr_mod.PortfolioRiskManager
PortfolioRiskConfig     = _pr_mod.PortfolioRiskConfig
OpenTradeRisk           = _pr_mod.OpenTradeRisk
RiskLevel               = _pr_mod.RiskLevel

LotSizer                = _ls_mod.LotSizer
LotSizingConfig         = _ls_mod.LotSizingConfig
LotSizingMethod         = _ls_mod.LotSizingMethod

# -- small builder helpers -----------------------------------------------------
def _otr(symbol="EURUSD", direction="BUY", lot=1000.0,
         entry=1.11, sl=1.10, balance=10_000.0) -> OpenTradeRisk:
    """
    OpenTradeRisk with auto-computed risk_percent.
    EURUSD: risk = abs(entry-sl) * lot * pip_value(10) / balance * 100
            = 0.01 * lot * 10 / 10000 * 100 = lot * 0.001  (balance=10k)
    So: lot=1000 -> 1.0%, lot=2000 -> 2.0%, lot=2010 -> 2.01%
    """
    return OpenTradeRisk(
        symbol=symbol, direction=direction, lot_size=lot,
        entry_price=entry, stop_loss=sl, account_balance=balance,
    )


def _ep(symbol="EURUSD", direction="BUY", risk_pct=1.0) -> ExposurePosition:
    return ExposurePosition(symbol=symbol, direction=direction,
                            risk_percent=risk_pct)


# ===============================================================================
# Topic 1 -- News Event Blocking
# ===============================================================================

class TestNewsEventBlocking(unittest.TestCase):
    """
    ISSUE:
      PortfolioRiskManager had no try/except before FIX #6, so any
      exception (e.g., corrupt OpenTradeRisk during NFP) would propagate
      uncaught and silently bypass all limits.

    EXACT PATCH (portfolio_risk.py):
      def check(self, trade, open_trades):
          try:
              return self._check_inner(trade, open_trades)
          except Exception as exc:
              logger.exception("PortfolioRiskManager.check error: %s", exc)
              if self._fail_mode is FailMode.FAIL_CLOSED:
                  return PortfolioCheckResult(can_trade=False, ...)
              logger.critical("FAIL_OPEN: portfolio check exception swallowed")
              return PortfolioCheckResult(can_trade=True, ...)

    PRODUCTION FORMULAS (verified):
      EURUSD pip_value = 10.0
      risk_pct = abs(entry-sl) * lot * pip_value / balance * 100
               = 0.01 * lot * 10 / 10000 * 100  (balance=10k, dist=0.01)
               = lot * 0.001 %
      -> lot=1000 -> 1.0%, lot=2000 -> 2.0%, lot=2010 -> 2.01%

    RISK IMPACT:
      Without limits: 5-lot (=5000-lot) NFP trade -> 5% account risk in
      one tick. With limits: blocked before entry.

    BACKWARD COMPAT:
      check(trade, open_trades) and check_async(trade, open_trades)
      signatures unchanged. PortfolioRiskConfig has no new required fields.
    """

    def setUp(self):
        self.mgr = PortfolioRiskManager()  # default FAIL_CLOSED, limits default

    # -- single trade risk > 2.0% (max_single_symbol_pct) --------------------
    def test_single_trade_over_limit_blocked(self):
        trade = _otr(lot=2010)       # 2.01% > 2.0% -> SINGLE_TRADE_RISK
        r = self.mgr.check(trade, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)
        self.assertEqual(r.risk_level, RiskLevel.BLOCKED)

    def test_single_trade_just_under_limit_allowed(self):
        # lot=1999 -> 1.999% < 2.0% -> allowed (FP-safe boundary)
        trade = _otr(lot=1999)
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)

    def test_single_trade_under_limit_allowed(self):
        trade = _otr(lot=1000)       # 1.0% < 2.0% -> allowed
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.SAFE)

    # -- portfolio total > 6.0% (max_portfolio_risk_pct) ----------------------
    def test_portfolio_total_over_limit_blocked(self):
        # 5 x 1.0% = 5.0% existing + 1.1% new = 6.1% > 6.0%
        existing  = [_otr(lot=1000) for _ in range(5)]
        new_trade = _otr(symbol="GBPUSD", lot=1100)   # 1.1%
        r = self.mgr.check(new_trade, existing)
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_RISK", r.reason)

    def test_portfolio_well_under_limit_allowed(self):
        # 4 x 1.0% = 4.0% + 1.0% new = 5.0% < 6.0% -> allowed (FP-safe)
        existing  = [_otr(lot=1000) for _ in range(4)]
        new_trade = _otr(symbol="GBPUSD", lot=1000)
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)

    # -- risk level ladder (0--60%: SAFE, 60--80%: WARNING, 80%+: CRITICAL) ----
    def test_risk_level_warning_above_60pct_of_limit(self):
        # total=4.0% > 6.0*0.6=3.6 but < 4.8 -> WARNING
        existing  = [_otr(lot=3000), _otr(lot=500)]   # 3.0+0.5=3.5%
        new_trade = _otr(symbol="GBPUSD", lot=500)   # 0.5% -> total=4.0%
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.WARNING)

    def test_risk_level_critical_above_80pct_of_limit(self):
        # total=5.0% > 6.0*0.8=4.8 -> CRITICAL
        existing  = [_otr(lot=3000), _otr(lot=2000)]  # 3.0+2.0=5.0%
        new_trade = _otr(symbol="GBPUSD", lot=0)      # 0.0% -> total=5.0%
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.CRITICAL)

    # -- remaining_cap ---------------------------------------------------------
    def test_remaining_cap_correct(self):
        existing  = [_otr(lot=3000)]   # existing=3.0%
        new_trade = _otr(symbol="GBPUSD", lot=1000)   # new=1.0% -> total=4.0%
        r = self.mgr.check(new_trade, existing)
        self.assertTrue(r.can_trade)
        # remaining_cap = max(0, 6.0 - existing_3.0) = 3.0
        self.assertAlmostEqual(r.remaining_cap, 3.0, places=4)

    # -- check_async mirrors check ---------------------------------------------
    def test_check_async_mirrors_check(self):
        trade      = _otr(lot=2010)   # over limit
        r_sync     = self.mgr.check(trade, [])
        r_async    = _run(self.mgr.check_async(trade, []))
        self.assertEqual(r_sync.can_trade, r_async.can_trade)
        self.assertEqual(r_sync.reason,    r_async.reason)


# ===============================================================================
# Topic 2 -- ATR Spike Robustness
# ===============================================================================

class TestATRSpikeRobustness(unittest.TestCase):
    """
    ISSUE:
      Before FIX #6, VolatilityFilter.check() had NO try/except.
      ZeroDivisionError (avg_atr=0) or corrupt history list -> propagate
      -> gate crashed -> trade silently allowed without logging.

    EXACT PATCH (volatility_filter.py):
      def check(self, current_atr, atr_history, current_spread,
                avg_spread, symbol=""):
          try:
              result = self._check_inner(...)
              self._cache[symbol] = _SymbolCache(...)
              return result
          except Exception as exc:
              logger.error("VolatilityFilter.check exception symbol=%s "
                           "fail_mode=%s: %s", symbol, self._fail_mode,
                           exc, exc_info=True)
              if self._fail_mode is FailMode.FAIL_CLOSED:
                  return VolatilityCheckResult(
                      can_trade=False,
                      reason=f"FAIL_CLOSED:VOLATILITY_GATE_ERROR:...")
              logger.critical("FAIL_OPEN: VolatilityFilter exception swallowed ...")
              return VolatilityCheckResult(
                  can_trade=True,
                  reason=f"FAIL_OPEN:VOLATILITY_GATE_ERROR:...")

    PRODUCTION THESHOLDS (VolatilityConfig defaults):
      atr_min_ratio   = 0.5   (ratio < 0.5  -> ATR_TOO_LOW)
      atr_max_ratio   = 3.0   (ratio > 3.0  -> ATR_TOO_HIGH)
      max_spread_ratio= 2.0   (ratio > 2.0  -> SPREAD_TOO_WIDE)
      min_atr_bars    = 5

    RISK IMPACT:
      ATR spike 4 x avg -> SL hit 4 x more often at 1 x sized lot
      -> actual loss = 4 x intended risk per trade.

    BACKWARD COMPAT:
      check(current_atr, atr_history, current_spread, avg_spread, symbol="")
      signature unchanged.
    """

    def setUp(self):
        self.vf      = VolatilityFilter()
        self.hist_10 = [0.001] * 10   # avg_atr = 0.001

    def _chk(self, atr, history=None, spread=0.0002, avg_spread=0.0002, sym="EURUSD"):
        h = history if history is not None else self.hist_10
        return self.vf.check(atr, h, spread, avg_spread, sym)

    # -- ATR too high ----------------------------------------------------------
    def test_atr_ratio_4x_blocked(self):
        r = self._chk(atr=0.004)       # ratio = 4.0 > 3.0
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)
        self.assertAlmostEqual(r.atr_ratio, 4.0, places=5)

    def test_atr_ratio_exactly_at_max_allowed(self):
        r = self._chk(atr=0.003)       # ratio = 3.0, NOT > 3.0 -> allowed
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.atr_ratio, 3.0, places=5)

    # -- ATR too low -----------------------------------------------------------
    def test_atr_ratio_04x_blocked(self):
        r = self._chk(atr=0.0004)      # ratio = 0.4 < 0.5
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_LOW", r.reason)

    def test_atr_ratio_exactly_at_min_allowed(self):
        r = self._chk(atr=0.0005)      # ratio = 0.5, NOT < 0.5 -> allowed
        self.assertTrue(r.can_trade)

    # -- spread too wide -------------------------------------------------------
    def test_spread_too_wide_blocked(self):
        r = self._chk(atr=0.001, spread=0.0005, avg_spread=0.0002)
        # spread_ratio = 2.5 > 2.0 -> blocked
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_WIDE", r.reason)
        self.assertGreater(r.spread_ratio, 2.0)

    def test_spread_exactly_at_limit_allowed(self):
        r = self._chk(atr=0.001, spread=0.0004, avg_spread=0.0002)
        # spread_ratio = 2.0, NOT > 2.0 -> allowed
        self.assertTrue(r.can_trade)

    # -- normal ATR ------------------------------------------------------------
    def test_normal_atr_allowed_with_correct_reason(self):
        r = self._chk(atr=0.0015)      # ratio = 1.5 -> normal
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "VOLATILITY_OK")

    # -- insufficient history --------------------------------------------------
    def test_insufficient_history_allowed_safe(self):
        r = self._chk(atr=0.004, history=[0.001] * 4)  # only 4 < min_atr_bars=5
        self.assertTrue(r.can_trade)   # safe pass-through
        self.assertIn("INSUFFICIENT_ATR_HISTORY", r.reason)

    # -- zero avg ATR -- safe guard --------------------------------------------
    def test_zero_avg_atr_safe_passthrough(self):
        r = self._chk(atr=0.001, history=[0.0] * 10)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "ZERO_AVG_ATR")

    # -- fail-closed on exception ----------------------------------------------
    def test_exception_fail_closed_blocks(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("boom")):
            with self.assertLogs("risk.volatility_filter", level="ERROR"):
                r = vf.check(0.001, self.hist_10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_exception_fail_open_allows(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("boom")):
            with self.assertLogs("risk.volatility_filter", level="ERROR"):
                r = vf.check(0.001, self.hist_10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)


# ===============================================================================
# Topic 3 -- Symbol-Specific Thresholds
# ===============================================================================

class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    ISSUE:
      A single global VolatilityConfig for all asset classes is incorrect.
      BTC normal daily ATR can be 8--10 x avg; EURUSD spike at 3.5 x is extreme.
      One threshold -> BTC perpetually blocked OR EURUSD crash ignored.

    EXACT PATCH (per-asset construction):
      gold_vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0))
      btc_vf  = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0))

    RISK IMPACT:
      Tight threshold on BTC -> false block during normal session.
      Loose threshold on Gold -> trade during actual crisis allowed.

    BACKWARD COMPAT:
      VolatilityFilter(config=None) still uses default thresholds.
      No API changes required.
    """

    def test_gold_tight_threshold_blocks_moderate_spike(self):
        # Gold ratio = 7.0/3.0 = 2.33 > atr_max=2.0 -> blocked
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        r  = vf.check(7.0, [3.0] * 10, 0.5, 0.5, "XAUUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_gold_tight_threshold_allows_normal_session(self):
        # Gold ratio = 5.0/4.0 = 1.25 < 2.0 -> allowed
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        r  = vf.check(5.0, [4.0] * 10, 0.5, 0.5, "XAUUSD")
        self.assertTrue(r.can_trade)

    def test_btc_loose_threshold_allows_high_volatility(self):
        # BTC ratio = 8000/1000 = 8.0 < atr_max=10.0 -> allowed
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        r  = vf.check(8000.0, [1000.0] * 10, 50.0, 50.0, "BTCUSD")
        self.assertTrue(r.can_trade)

    def test_btc_loose_threshold_blocks_extreme_crash(self):
        # BTC ratio = 11000/1000 = 11.0 > 10.0 -> blocked
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        r  = vf.check(11000.0, [1000.0] * 10, 50.0, 50.0, "BTCUSD")
        self.assertFalse(r.can_trade)

    def test_forex_default_threshold_normal_allowed(self):
        # Default max=3.0; EURUSD ratio=2.5 -> allowed
        vf = VolatilityFilter()
        r  = vf.check(0.0025, [0.001] * 10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_independent_instances_no_cache_bleed(self):
        # Two independent instances; results don't bleed between them
        vf_gold = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        vf_btc  = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        r_gold  = vf_gold.check(7.0, [3.0]*10, 0.5, 0.5, "XAUUSD")    # 2.33>2.0 -> blocked
        r_btc   = vf_btc.check(8000.0, [1000.0]*10, 50.0, 50.0, "BTCUSD")  # 8.0<10.0 -> ok
        self.assertFalse(r_gold.can_trade)
        self.assertTrue(r_btc.can_trade)

    def test_custom_min_atr_bars_under_threshold_returns_insufficient(self):
        # min_atr_bars=10; only 7 bars supplied -> INSUFFICIENT_ATR_HISTORY
        vf = VolatilityFilter(VolatilityConfig(min_atr_bars=10))
        r  = vf.check(0.001, [0.001] * 7, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("INSUFFICIENT_ATR_HISTORY", r.reason)


# ===============================================================================
# Topic 4 -- Gold Pip Value
# ===============================================================================

class TestGoldPipValue(unittest.TestCase):
    """
    ISSUE (FIX #4):
      Both lot_sizing.py and portfolio_risk.py had:
        "XAUUSD": 10.0   <-- 10 x too high
      Correct value: Gold pip = $0.01/oz x 100 oz standard lot = $1.00

    EXACT PATCH:
      lot_sizing.py:
        "XAUUSD":  1.0,   # Gold -- pip=$0.01, 100 oz lot

      portfolio_risk.py:
        "XAUUSD":  1.0,   # Gold: $1 per 0.01 pip (1 cent per point)

    RISK IMPACT:
      With pip_value=10: lot sizer computed lot/10 -> underexposed by 10 x.
      Actual position risk was only 10% of stated risk.
      A 1% targeted Gold trade actually risked 0.1% -> limits meaningless.

    BACKWARD COMPAT:
      LotSizer.get_pip_value(), _get_pip_value(), _get_pip_value_with_source()
      signatures unchanged. Alias/suffix resolution unchanged.
    """

    # -- lot_sizing pip table -------------------------------------------------
    def test_ls_xauusd_pip_is_1(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_ls_xauusd_not_10(self):
        self.assertNotEqual(_ls_mod._PIP_VALUE_TABLE["XAUUSD"], 10.0)

    def test_ls_gold_alias_resolves_to_1(self):
        self.assertEqual(LotSizer().get_pip_value("GOLD"), 1.0)

    def test_ls_xauusd_broker_suffix_m_resolves_to_1(self):
        self.assertEqual(LotSizer().get_pip_value("XAUUSDm"), 1.0)

    def test_ls_xauusd_broker_suffix_pro_resolves_to_1(self):
        self.assertEqual(LotSizer().get_pip_value("XAUUSDpro"), 1.0)

    # -- lot_sizing calculation with pip=1.0 ----------------------------------
    def test_ls_gold_lot_correct(self):
        # 1% of $10k = $100; SL=100 pips; lot = 100/(100 x 1.0) = 1.0
        sizer  = LotSizer(LotSizingConfig(
            risk_percent=1.0, min_lot=0.01, max_lot=5.0, lot_step=0.01
        ))
        r = _run(sizer.calculate("XAUUSD", 10_000, 100))
        self.assertAlmostEqual(r.lot_size,     1.0, places=2)
        self.assertAlmostEqual(r.risk_percent, 1.0, places=2)

    # -- portfolio_risk pip table ---------------------------------------------
    def test_pr_xauusd_pip_is_1(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_pr_xauusd_not_10(self):
        self.assertNotEqual(_pr_mod._PIP_VALUE_TABLE["XAUUSD"], 10.0)

    def test_pr_gold_alias_resolves_to_1(self):
        self.assertEqual(_pr_mod._get_pip_value("GOLD"), 1.0)

    def test_pr_xauusd_suffix_resolves_to_1(self):
        self.assertEqual(_pr_mod._get_pip_value("XAUUSDm"), 1.0)

    # -- OpenTradeRisk risk calculation with pip=1.0 --------------------------
    def test_pr_gold_opentraderisk_risk_correct(self):
        # dist=50, lot=1.0, pip_val=1.0, bal=10k -> risk=50x1 x 1/10000x100=0.5%
        trade = OpenTradeRisk(
            symbol="XAUUSD", direction="BUY", lot_size=1.0,
            entry_price=1950.0, stop_loss=1900.0, account_balance=10_000.0,
        )
        self.assertAlmostEqual(trade.risk_percent, 0.5, places=2)

    # -- Silver unchanged ------------------------------------------------------
    def test_silver_xAgusd_pip_is_50(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XAGUSD"C, 50.0)
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["XAGUSD"], 50.0)


# ===============================================================================
# Topic 5 -- Crypto Pip Value
# ===============================================================================

class TestCryptoPipValue(unittest.TestCase):
    """
    ISSUE:
      Before FIX #4, ETHUSD pip_value=0.01 (100 x too small).
      This caused lot sizer to return 100 x oversized lots.

    EXACT PATCH (lot_sizing.py):
      "BTCUSD": 1.0, "ETHUSD": 1.0, "LTCUSD": 1.0,
      "BNBUSD": 1.0, "XRPUSD": 1.0,

    RISK IMPACT:
      ETH at pip=0.01: lot = $100/(100 x 0.01) = 100 lots -> account blow.
      ETH at pip=1.0:  lot = $100/(100 x 1.0)  = 1.0 lot  -> correct.

    BACKWARD COMPAT:
      get_pip_value() and _resolve_pip_value() signatures unchanged.
      Alias/suffix resolution works identically.
    """

    # -- pip table -- both modules ---------------------------------------------
    def test_ls_btcusd_is_1(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["BTCUSD"], 1.0)

    def test_ls_ethusd_is_1(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["ETHUSD"], 1.0)

    def test_ls_ltcusd_is_1(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["LTCUSD"], 1.0)

    def test_ls_bnbusd_is_1(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["BNBUSD"], 1.0)

    def test_ls_xrpusd_is_1(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XRPUSD"], 1.0)

    # -- alias resolution ------------------------------------------------------
    def test_ls_btc_alias_is_1(self):
        self.assertEqual(LotSizer().get_pip_value("BTC"), 1.0)

    def test_ls_bitcoin_alias_is_1(self):
        self.assertEqual(LotSizer().get_pip_value("BITCOIN"), 1.0)

    def test_ls_eth_alias_is_1(self):
        self.assertEqual(LotSizer().get_pip_value("ETH"), 1.0)

    def test_ls_btcusd_broker_suffix_is_1(self):
        self.assertEqual(LotSizer().get_pip_value("BTCUSDm"), 1.0)

    # -- lot calculation with pip=1.0 ------------------------------------------
    def test_ls_btc_lot_correct(self):
        # 1% of $10k=$100; SL=500 pips; lot=100/(500 x 1.0)=0.20
        sizer  = LotSizer(LotSizingConfig(
            risk_percent=1.0, min_lot=0.01, lot_step=0.01
        ))
        r = _run(sizer.calculate("BTCUSD", 10_000, 500))
        self.assertAlmostEqual(r.lot_size, 0.20, places=2)

    # -- portfolio_risk crypto table -------------------------------------------
    def test_pr_btcusd_is_1(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["BTCUSD"], 1.0)

    def test_pr_ethusd_is_1(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["ETHUSD"], 1.0)

    # -- OpenTradeRisk with ETH pip=1.0 ----------------------------------------
    def test_pr_eth_opentraderisk_risk_correct(self):
        # dist=100, lot=0.5, pip_val=1.0, bal=10k -> 0.5%
        trade = OpenTradeRisk(
            symbol="ETHUSD", direction="BUY", lot_size=0.5,
            entry_price=2100.0, stop_loss=2000.0, account_balance=10_000.0,
        )
        self.assertAlmostEqual(trade.risk_percent, 0.5, places=2)


# ===============================================================================
# Topic 6 -- Exposure Calculation
# ===============================================================================

class TestExposureCalculation(unittest.TestCase):
    """
    ISSUE:
      ExposureControlEngine.check() had no try/except before FIX #6.
      Any AttributeError from corrupt ExposurePosition -> propagate -> bypass.
      Before FIX #5: new_risk_percent was hardcoded 1.0 in orchestrator.

    EXACT PATCH (exposure_control.py):
      def check(self, new_symbol, new_direction, new_risk_percent,
                open_positions=None, account_balance=10_000.0):
          try:
              return self._check_inner(...)  # real new_risk_percent used
          except Exception as exc:
              logger.exception("...fail_mode=%s", self._fail_mode, exc_info=True)
              if FAIL_CLOSED: return ExposureCheckResult(can_trade=False, ...)
              return ExposureCheckResult(can_trade=True,
                  reason='FAIL_OPEN_EXCEPTION_IGNORED')

    PRODUCTION DEFAULTS (ExposureConfig):
      max_total_risk_percent = 5.0
      max_risk_per_symbol    = 2.0
      max_open_trades        = 5

    RISK IMPACT:
      Hardcoded 1.0: a 3% EURUSD trade wouldn't trigger MAX_SYMBOL_RISK=2.0
      because the check saw 1.0, not 3.0. Direct unbounded exposure possible.

    BACKWARD COMPAT:
      check(..., new_risk_percent, ...) parameter propagated correctly.
      get_snapshot() unchanged signature.
    """

    def setUp(self):
        self.engine = ExposureControlEngine()

    def _chk(self, symbol="GBPUSD", direction="BUY", new_risk=1.0,
             positions=None, balance=10_000.0):
        return self.engine.check(symbol, direction, new_risk,
                                  positions or [], balance)

    # -- MAX_TOTAL_RISK (5.0%) -------------------------------------------------
    def test_total_risk_over_limit_blocked(self):
        # existing=4.0% + new=1.5% = 5.5% > 5.0%
        ops = [_ep("EURUSD", risk_pct=2.0), _ep("GBPUSD", risk_pct=2.0)]
        r = self._chk(symbol="USDJPY", new_risk=1.5, positions=ops)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_TOTAL_RISK", r.reason)

    def test_total_risk_at_limit_allowed(self):
        # existing=4.0% + new=1.0% = 5.0% = limit -> not > -> allowed
        ops = [_ep("EURUSD", risk_pct=2.0), _ep("GBPUSD", risk_pct=2.0)]
        r = self._chk(symbol="USDJPY", new_risk=1.0, positions=ops)
        self.assertTrue(r.can_trade)

    def test_projected_total_risk_propagated_correctly(self):
        # FIX #5 regression: projected must use actual new_risk_percent
        ops = [_ep("EURUSD", risk_pct=1.5)]
        r = self._chk(new_risk=2.0, positions=ops)
        # projected = 1.5 + 2.0 = 3.5  (NOT 1.5 + 1.0 = 2.5)
        self.assertAlmostEqual(r.projected_total_risk, 3.5, places=5)

    # -- MAX_SYMBOL_RISK (2.0%) ------------------------------------------------
    def test_symbol_risk_over_limit_blocked(self):
        # EURUSD: existing 1.5% + new 1.0% = 2.5% > 2.0%
        ops = [_ep("EURUSD", risk_pct=1.5)]
        r = self._chk(symbol="EURUSD", new_risk=1.0, positions=ops)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)
        self.assertIn("EURUSD", r.reason)

    def test_symbol_risk_at_limit_allowed(self):
        # EURUSD: existing 1.0% + new 1.0% = 2.0% = limit
        ops = [_ep("EURUSD", risk_pct=1.0)]
        r = self._chk(symbol="EURUSD", new_risk=1.0, positions=ops)
        self.assertTrue(r.can_trade)

    # -- MAX_OPEN_TRADES (5) ---------------------------------------------------
    def test_max_trades_at_limit_blocked(self):
        # 5 existing x 0.5% = 2.5%; new 0.5% -> total=3.0% < 5.0%
        # But len(ops)=5 >= max_open_trades=5 -> MAX_OPEN_TRADES blocked
        ops = [_ep(f"S{i}", risk_pct=0.5) for i in range(5)]
        r = self._chk(symbol="NEW", new_risk=0.5, positions=ops)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_OPEN_TRADES", r.reason)

    def test_max_trades_under_limit_allowed(self):
        ops = [_ep(f"S{i}") for i in range(4)]
        r = self._chk(positions=ops)
        self.assertTrue(r.can_trade)

    # -- available_risk --------------------------------------------------------
    def test_available_risk_correct(self):
        ops = [_ep("EURUSD", risk_pct=2.0)]
        r = self._chk(new_risk=1.0, positions=ops)
        # avail = max_total(5.0) - existing(2.0) = 3.0
        self.assertAlmostEqual(r.available_risk, 3.0, places=5)

    # -- empty positions -------------------------------------------------------
    def test_no_positions_allowed(self):
        r = self._chk(new_risk=1.0, positions=[])
        self.assertTrue(r.can_trade)
        self.assertEqual(r.current_total_risk, 0.0)
        self.assertAlmostEqual(r.projected_total_risk, 1.0, places=5)

    # -- fail-closed on exception ----------------------------------------------
    def test_exception_fail_closed_blocks(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=AttributeError("corrupt")):
            with self.assertLogs("risk.exposure_control", level="ERROR"):
                r = ec.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_exception_fail_open_allows(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError("explode")):
            with self.assertLogs("risk.exposure_control", level="ERROR"):
                r = ec.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    # -- get_snapshot fail-mode ------------------------------------------------
    def test_get_snapshot_fail_closed_reraises(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_snapshot_inner', side_effect=RuntimeError("snap")):
            with self.assertRaises(RuntimeError):
                ec.get_snapshot([])

    def test_get_snapshot_fail_open_returns_empty_snapshot(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(ec, '_snapshot_inner', side_effect=RuntimeError("snap")):
            snap = ec.get_snapshot([])
        self.assertEqual(snap.total_risk_percent, 0.0)
        self.assertEqual(snap.open_trade_count,   0)


# ===============================================================================
# Topic 7 -- Fail-Closed Behavior
# ===============================================================================

class TestFailClosedBehavior(unittest.TestCase):
    """
    ISSUE (FIX #6):
      Before fix:
        CorrelationFilter: except: allow_trade=True  (silent! no log!)
        ExposureControl:   no try/except
        VolatilityFilter:  no try/except
        PortfolioRisk:     no try/except
        No configurable FailMode -- all hardcoded to allow on error.

    EXACT PATCH -- fail_mode.py (new file):
      class FailMode(str, Enum):
          FAIL_CLOSED = "FAIL_CLOSED"   # safe default: block on exception
          FAIL_OPEN   = "FAIL_OPEN"     # permissive: allow on exception

      def coerce(value) -> FailMode:
          if isinstance(value, FailMode): return value
          return FailMode(str(value).upper().strip())

      Each gate:  self._fail_mode = _coerce_fm(fail_mode or config.fail_mode)
      Exception:  logger.critical(..., exc_info=True)  # ALWAYS logged
      FAIL_CLOSED -> block; FAIL_OPEN -> allow + extra CRITICAL log

    RISK IMPACT:
      Before: any exception in correlation gate -> allow trade silently.
      After:  exception always logged; FAIL_CLOSED blocks; never silent.

    BACKWARD COMPAT:
      All constructors still work with no arguments (FAIL_CLOSED default).
      String fail_mode accepted and coerced ("FAIL_OPEN" or "fail_open").
    """

    # -- Single Source of Truth -- all modules use identical FailMode class ---
    def test_sst_vf_failmode_is_canonical(self):
        self.assertIs(_vf_mod.FailMode, _fm_mod.FailMode)

    def test_sst_cf_failmode_is_canonical(self):
        self.assertIs(_cf_mod.FailMode, _fm_mod.FailMode)

    def test_sst_ec_failmode_is_canonical(self):
        self.assertIs(_ec_mod.FailMode, _fm_mod.FailMode)

    def test_sst_pr_failmode_is_canonical(self):
        self.assertIs(_pr_mod.FailMode, _fm_mod.FailMode)

    # -- coerce() --------------------------------------------------------------
    def test_coerce_uppercase_string(self):
        self.assertIs(coerce("FAIL_CLOSED"), FailMode.FAIL_CLOSED)

    def test_coerce_lowercase_string(self):
        self.assertIs(coerce("fail_open"),   FailMode.FAIL_OPEN)

    def test_coerce_enum_passthrough(self):
        self.assertIs(coerce(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)

    def test_coerce_invalid_value_raises_ValueError(self):
        with self.assertRaises(ValueError):
            coerce("UNKNOWN_MODE")

    # -- str Enum: FailMode values equal plain strings -------------------------
    def test_failmode_str_enum_closed(self):
        self.assertEqual(FailMode.FAIL_CLOSED, "FAIL_CLOSED")

    def test_failmode_str_enum_open(self):
        self.assertEqual(FailMode.FAIL_OPEN, "FAIL_OPEN")

    # -- default FAIL_CLOSED on all 4 gates -----------------------------------
    def test_volatility_filter_defaults_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_correlation_filter_defaults_fail_closed(self):
        self.assertIs(CorrelationFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_exposure_engine_defaults_fail_closed(self):
        self.assertIs(ExposureControlEngine()._fail_mode, FailMode.FAIL_CLOSED)

    def test_portfolio_risk_defaults_fail_closed(self):
        self.assertIs(PortfolioRiskManager()._fail_mode, FailMode.FAIL_CLOSED)

    # -- kwarg overrides config ------------------------------------------------
    def test_cf_kwarg_overrides_config_fail_mode(self):
        cfg = CorrelationFilterConfig(fail_mode=FailMode.FAIL_CLOSED)
        cf  = CorrelationFilter(config=cfg, fail_mode="FAIL_OPEN")
        self.assertIs(cf._fail_mode, FailMode.FAIL_OPEN)

    def test_ec_kwarg_overrides_config_fail_mode(self):
        cfg = ExposureConfig(fail_mode=FailMode.FAIL_CLOSED)
        ec  = ExposureControlEngine(config=cfg, fail_mode="FAIL_OPEN")
        self.assertIs(ec._fail_mode, FailMode.FAIL_OPEN)

    # -- every exception is logged (never silent) ------------------------------
    def test_vf_exception_always_logged_fail_closed(self):
        vf = VolatilityFilter()
        with patch.object(vf, '_check_inner', side_effect=ValueError("vf_fail")):
            with self.assertLogs("risk.volatility_filter", level="ERROR") as cm:
                r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertTrue(any("vf_fail" in m or "VolatilityFilter" in m
                            for m in cm.output))

    def test_vf_exception_always_logged_fail_open(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, '_check_inner', side_effect=ValueError("vf_open")):
            with self.assertLogs("risk.volatility_filter", level="ERROR") as cm:
                r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertTrue(len(cm.output) >= 1)   # at least one log line

    def test_cf_exception_always_logged(self):
        cf = CorrelationFilter()
        async def _boom(*a, **kw): raise RuntimeError("cf_fail")
        with patch.object(cf, '_check_inner', side_effect=_boom):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL") as cm:
                r = _run(cf.check("EURUSD", "BUY", []))
        self.assertFalse(r.can_trade)
        self.assertTrue(any("FABL_CLOSED" in m or "cf_fail" in m
                            for m in cm.output))

    def test_ec_exception_always_logged(self):
        ec = ExposureControlEngine()
        with patch.object(ec, '_check_inner', side_effect=AttributeError("ec_fail")):
            with self.assertLogs("risk.exposure_control", level="ERROR") as cm:
                r = ec.check("EURUSD", "BUY", 1.0, [], 10_000)
        self.assertFalse(r.can_trade)
        self.assertTrue(len(cm.output) >= 1)

    def test_pr_exception_always_logged(self):
        pr    = PortfolioRiskManager()
        trade = _otr(lot=1000)
        with patch.object(pr, '_check_inner', side_effect=RuntimeError("pr_fail")):
            with self.assertLogs("risk.portfolio_risk", level="ERROR") as cm:
                r = pr.check(trade, [])
        self.assertFalse(r.can_trade)
        self.assertTrue(len(cm.output) >= 1)


# ===============================================================================
# Topic 8 -- Portfolio Correlation Calculations
# ===============================================================================

class TestPortfolioCorrelationCalcs(unittest.TestCase):
    """
    ISSUE (FIX #6):
      CorrelationFilter.check() had NO outer try/except.
      Per-pair exception -> inner catch -> corr=0.0 -> allowed (OK).
      Outer exception -> propagate -> bypassed fail_mode gate entirely.

    EXACT PATCH (correlation_filter.py):
      async def check(self, symbol, direction, open_positions=None):
          try:
              return await self._check_inner(symbol, direction, open_positions)
          except Exception as exc:
              logger.critical("CorrelationFilter exception symbol=%s "
                              "fail_mode=%s: %s", symbol, self._fail_mode,
                              exc, exc_info=True)
              if self._fail_mode is FailMode.FAIL_CLOSED:
                  return CorrelationCheckResult(
                      can_trade=False,
                      reason=f'FAIL_CLOSED:CORR_EXCEPTION:{type(exc).__name__}')
              logger.critical("FAIL_OPEN: CorrelationFilter exception swallowed ...")
              return CorrelationCheckResult(
                  can_trade=True, reason='FAIL_OPEN:CORR_EXCEPTION_IGNORED')

    PRODUCTION LOGIC in _check_inner:
      - Skip same-symbol positions
      - Per-pair engine crash -> corr=0.0 (inner except swallows)
      - abs(corr) >= max_corr -> CORR_TOO_HIGH  (uses abs for negative corr)

    RISK IMPACT:
      Before: outer crash -> propagate -> FAIL_OPEN without log -> dangerous.
      After: always logged; configurable block vs allow.

    BACKWARD COMPAT:
      async check(symbol, direction, open_positions=None) signature unchanged.
      CorrelationFilterConfig defaults unchanged (max_corr=0.85).
    """

    def _engine(self, corr_map: dict):
        engine = MagicMock()
        async def _get(s1, s2):
            return (corr_map.get((s1, s2)) or
                    corr_map.get((s2, s1)) or 0.0)
        engine.get_correlation = _get
        return engine

    # -- high positive correlation blocks --------------------------------------
    def test_high_positive_corr_blocked(self):
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=self._engine({("EURUSD","GBPUSD"): 0.92}),
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("CORR_TOO_HIGH", r.reason)
        self.assertAlmostEqual(abs(r.correlation), 0.92, places=5)

    def test_high_negative_corr_blocked(self):
        # abs(-0.90) = 0.90 >= 0.85 -> blocked
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=self._engine({("EURUSD","USDCHF"): -0.90}),
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "USDCHF"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("CORR_TOO_HIGH", r.reason)

    def test_low_corr_allowed(self):
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=self._engine({("EURUSD","USDJPY"): 0.30}),
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "USDJPY"}]))
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "CORR_OK")

    def test_corr_exactly_at_threshold_blocked(self):
        # abs(0.85) >= 0.85 -> blocked (condition is >=)
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=self._engine({("EURUSD","GBPUSD"): 0.85}),
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertFalse(r.can_trade)

    # -- same-symbol skip ------------------------------------------------------
    def test_same_symbol_position_skipped_engine_not_called(self):
        call_count = [0]
        async def _counting_get(s1, s2):
            call_count[0] += 1
            return 0.99   # would block if called
        engine = MagicMock()
        engine.get_correlation = _counting_get
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=engine,
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "EURUSD"}]))
        self.assertTrue(r.can_trade)
        self.assertEqual(call_count[0], 0)   # engine never called

    # -- no positions / no engine ----------------------------------------------
    def test_empty_positions_allowed(self):
        cf = CorrelationFilter(correlation_engine=self._engine({}))
        r = _run(cf.check("EURUSD", "BUY", []))
        self.assertTrue(r.can_trade)

    def test_none_positions_allowed(self):
        cf = CorrelationFilter(correlation_engine=self._engine({}))
        r = _run(cf.check("EURUSD", "BUY", None))
        self.assertTrue(r.can_trade)

    def test_no_engine_allowed_with_reason(self):
        cf = CorrelationFilter()   # engine=None
        r  = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)
        self.assertIn("NO_POSITIONS_OR_ENGINE", r.reason)

    # -- per-pair engine crash -> corr=0.0 -> allowed --------------------------
    def test_per_pair_engine_crash_swallowed_allows(self):
        engine = MagicMock()
        async def _crash(s1, s2): raise RuntimeError("DB timeout")
        engine.get_correlation = _crash
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=engine,
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertTrue(r.can_trade)   # per-pair crash -> corr=0 -> allowed

    # -- outer exception -- fail-mode ------------------------------------------
    def test_outer_exception_fail_closed_blocks(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        async def _boom(*a, **kw): raise RuntimeError("outer crash")
        with patch.object(cf, '_check_inner', side_effect=_boom):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = _run(cf.check("EURUSD", "BUY", []))
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_outer_exception_fail_open_allows(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        async def _boom(*a, **kw): raise RuntimeError("outer crash")
        with patch.object(cf, '_check_inner', side_effect=_boom):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = _run(cf.check("EURUSD", "BUY", []))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    # -- pair_checked populated ------------------------------------------------
    def test_pair_checked_populated_on_block(self):
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=self._engine({("EURUSD","GBPUSD"): 0.92}),
        )
        r = _run(cf.check("EURUSD", "BUY", [{"symbol": "GBPUSD"}]))
        self.assertFalse(r.can_trade)
        self.assertEqual(r.pair_checked, "GBPUSD")

    # -- early exit on first breach --------------------------------------------
    def test_first_breach_early_exit_stops_at_first_correlated_pair(self):
        call_log = []
        async def _get(s1, s2):
            call_log.append((s1, s2))
            if "GBPUSD" in (s1, s2): return 0.92   # high -> block
            return 0.1
        engine = MagicMock()
        engine.get_correlation = _get
        cf = CorrelationFilter(
            config=CorrelationFilterConfig(max_corr=0.85),
            correlation_engine=engine,
        )
        positions = [{"symbol": "GBPUSD"}, {"symbol": "USDJPY"}]
        r = _run(cf.check("EURUSD", "BUY", positions))
        self.assertFalse(r.can_trade)
        self.assertEqual(len(call_log), 1)   # stopped after GBPUSD
        self.assertIn("GBPUSD", call_log[0])


# ===============================================================================
# Integration -- cross-gate verification
# ===============================================================================

class TestIntegration(unittest.TestCase):

    def test_real_risk_propagated_to_exposure_gate_not_hardcoded_1(self):
        """FIX #5 regression: orchestrator must pass actual risk%, not 1.0."""
        ec  = ExposureControlEngine(config=ExposureConfig(max_risk_per_symbol=2.0))
        ops = [_ep("EURUSD", risk_pct=1.5)]
        r   = ec.check("EURUSD", "BUY", 1.0, ops, 10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)
        self.assertAlmostEqual(r.projected_total_risk, 2.5, places=5)

    def test_gold_pip_value_consistent_between_sizer_and_portfolio_risk(self):
        """Both modules must agree on XAUUSD=1.0, not one at 10.0."""
        ls_pip = LotSizer().get_pip_value("XAUUSD")
        pr_pip = _pr_mod._get_pip_value("XAUUSD")
        self.assertEqual(ls_pip, 1.0)
        self.assertEqual(pr_pip, 1.0)
        self.assertEqual(ls_pip, pr_pip)

    def test_all_gates_default_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode,      FailMode.FAIL_CLOSED)
        self.assertIs(CorrelationFilter()._fail_mode,     FailMode.FAIL_CLOSED)
        self.assertIs(ExposureControlEngine()._fail_mode, FailMode.FAIL_CLOSED)
        self.assertIs(PortfolioRiskManager()._fail_mode,  FailMode.FAIL_CLOSED)

    def test_exposure_snapshot_aggregates_correctly(self):
        ec  = ExposureControlEngine()
        ops = [
            _ep("EURUSD", "BUY",  risk_pct=1.0),
            _ep("GBPUSD", "BUY",  risk_pct=1.5),
            _ep("EURUSD", "SELL", risk_pct=0.5),
        ]
        snap = ec.get_snapshot(ops)
        self.assertAlmostEqual(snap.total_risk_percent,       3.0, places=5)
        self.assertAlmostEqual(snap.risk_by_symbol["EURUSD"], 1.5, places=5)
        self.assertAlmostEqual(snap.risk_by_symbol["GBPUSD"], 1.5, places=5)

    def test_volatility_and_correlation_gates_independent(self):
        """ATR spike blocking does NOT affect correlation gate."""
        vf = VolatilityFilter()
        cf = CorrelationFilter()   # no engine -> always allowed
        r_vf = vf.check(0.004, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        r_cf = _run(cf.check("EURUSD", "BUY", None))
        self.assertFalse(r_vf.can_trade)
        self.assertTrue(r_cf.can_trade)


if __name__ == "__main__":
    unittest.main(verbosity=2)
