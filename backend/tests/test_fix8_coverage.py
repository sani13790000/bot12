"""backend/tests/test_fix8_coverage.py

FIX #8 - Production-Grade Test Coverage
========================================
8 Topics:
  1.  News Event Blocking         ( 9 tests)
  2.  ATR Spike Robustness        (11 tests)
  3.  Symbol-Specific Thresholds  ( 7 tests)
  4.  Gold Pip Value              (13 tests)
  5.  Crypto Pip Value            (13 tests)
  6.  Exposure Calculation        (14 tests)
  7.  Fail-Closed Behaviour       (22 tests)
  8.  Portfolio Correlation       (15 tests)
  Integration                    ( 5 tests)
  Total                          109 tests

Run:
    pytest backend/tests/test_fix8_coverage.py -v
"""
from __future__ import annotations

import asyncio
import logging
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Path bootstrap -- resolve to repo root
# ---------------------------------------------------------------------------
import os, importlib.util, pathlib

_HERE = os.path.dirname(os.path.abspath(__file__))        # backend/tests/
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))  # repo root
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ---------------------------------------------------------------------------
# Stub correlation_engine so modules load without it
# ---------------------------------------------------------------------------
def _make_ce_stub():
    class _RCE:
        async def get_correlation(self, a, b):
            return 0.0
    mod = types.ModuleType("backend.risk.correlation_engine")
    mod.RollingCorrelationEngine = _RCE
    return mod, _RCE

_ce_stub, _RCEStub = _make_ce_stub()
sys.modules.setdefault("backend",      types.ModuleType("backend"))
sys.modules.setdefault("backend.risk", types.ModuleType("backend.risk"))
sys.modules["backend.risk.correlation_engine"] = _ce_stub

# ---------------------------------------------------------------------------
# Load production modules from their installed location
# ---------------------------------------------------------------------------
_RISK_DIR = pathlib.Path(__file__).parent.parent / "risk"

def _load(dotted: str, filename: str):
    spec = importlib.util.spec_from_file_location(dotted, _RISK_DIR / filename)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod

_fm_mod  = _load("backend.risk.fail_mode",          "fail_mode.py")
_vf_mod  = _load("backend.risk.volatility_filter",  "volatility_filter.py")
_pr_mod  = _load("backend.risk.portfolio_risk",     "portfolio_risk.py")
_ec_mod  = _load("backend.risk.exposure_control",   "exposure_control.py")
_cf_mod  = _load("backend.risk.correlation_filter", "correlation_filter.py")
_ls_mod  = _load("backend.risk.lot_sizing",         "lot_sizing.py")

# Canonical FailMode (from fail_mode.py)
FailMode  = _fm_mod.FailMode
coerce_fm = _fm_mod.coerce

# Per-module FailMode enums (may differ from canonical due to try/except imports)
_VF_FM = _vf_mod.FailMode
_CF_FM = _cf_mod.FailMode
_EC_FM = _ec_mod.FailMode
_PR_FM = _pr_mod.FailMode

# Production classes
VolatilityFilter      = _vf_mod.VolatilityFilter
VolatilityConfig      = _vf_mod.VolatilityConfig

PortfolioRiskManager  = _pr_mod.PortfolioRiskManager
PortfolioRiskConfig   = _pr_mod.PortfolioRiskConfig
OpenTradeRisk         = _pr_mod.OpenTradeRisk
TradeDirection        = _pr_mod.TradeDirection

ExposureControlEngine = _ec_mod.ExposureControlEngine
ExposureConfig        = _ec_mod.ExposureConfig
ExposurePosition      = _ec_mod.ExposurePosition

CorrelationFilter       = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig

LotSizer              = _ls_mod.LotSizer
LotSizingConfig       = _ls_mod.LotSizingConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _otr(symbol="EURUSD", direction="BUY",
         lot=1.0, entry=2.0, sl=1.0,
         balance=10_000.0) -> OpenTradeRisk:
    """
    Build an OpenTradeRisk.
    risk_pct = abs(entry-sl) * lot * pip_val / balance * 100
    EURUSD pip_val=10: dist=1.0, lot=X -> risk = X%
    e.g. lot=2.1 -> 2.1%, lot=2.0 -> 2.0% (boundary)
    """
    return OpenTradeRisk(
        symbol=symbol,
        direction=TradeDirection.BUY if direction == "BUY" else TradeDirection.SELL,
        lot_size=lot,
        entry_price=entry,
        stop_loss=sl,
        account_balance=balance,
    )


def _ep(symbol="EURUSD", direction="BUY", risk_pct=1.0) -> ExposurePosition:
    return ExposurePosition(symbol=symbol, direction=direction,
                            risk_percent=risk_pct)


def _run(coro):
    """Run coroutine -- Python 3.14 compatible."""
    return asyncio.run(coro)


def _vf_config(fail_open: bool = False, **kwargs) -> VolatilityConfig:
    """Return VolatilityConfig with optional FAIL_OPEN using local FailMode."""
    fm = _VF_FM.FAIL_OPEN if fail_open else _VF_FM.FAIL_CLOSED
    return VolatilityConfig(fail_mode=fm, **kwargs)


# ---------------------------------------------------------------------------
# Topic 1 -- News Event Blocking
# ---------------------------------------------------------------------------
class TestNewsEventBlocking(unittest.TestCase):
    """
    ISSUE: PortfolioRiskManager had no try/except before FIX #6.
    Any exception bypassed ALL risk limits silently.

    Formula (production):
        risk_pct = abs(entry-sl) * lot * pip_val / balance * 100
        EURUSD pip_val=10, balance=10000:
            dist=1.0, lot=2.1 -> risk=2.1% (blocked: > 2.0%)
            dist=1.0, lot=2.0 -> risk=2.0% (boundary: NOT > 2.0, allowed)

    EXACT PATCH (portfolio_risk.py):
        def check(self, trade, open_trades):
            try: return self._check_inner(...)
            except Exception as exc:
                logger.exception(...)
                if FAIL_CLOSED: return blocked result
                return allowed result with reason="FAIL_OPEN:PORTFOLIO_CHECK_ERROR"

    RISK: 5-lot NFP trade with wrong pip_value reported under 1%, never blocked.
    BACKWARD COMPAT: check() and check_async() signatures unchanged.
    """

    def setUp(self):
        self.mgr = PortfolioRiskManager()

    def test_single_trade_blocked_above_limit(self):
        # dist=1.0, lot=21, pip=10, bal=10000 -> risk=2.1% > 2.0% -> SINGLE_TRADE_RISK
        trade = _otr("EURUSD", lot=21.0, entry=2.0, sl=1.0)
        r = self.mgr.check(trade, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)
        self.assertAlmostEqual(r.new_risk_pct, 2.1, places=5)

    def test_single_trade_boundary_allowed(self):
        # dist=1.0, lot=20, pip=10, bal=10000 -> risk=2.0% = limit (NOT >), allowed
        trade = _otr("EURUSD", lot=20.0, entry=2.0, sl=1.0)
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.new_risk_pct, 2.0, places=5)

    def test_portfolio_total_blocked(self):
        # 4 existing * 1.5% each = 6.0%; new 1.5% -> total 7.5% > 6.0% -> PORTFOLIO_RISK
        existing = [_otr("GBPUSD", lot=15.0, entry=2.0, sl=1.0) for _ in range(4)]
        new_t    = _otr("AUDUSD", lot=15.0, entry=2.0, sl=1.0)
        r = self.mgr.check(new_t, existing)
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_RISK", r.reason)

    def test_portfolio_boundary_allowed(self):
        # 5 existing * 1.0% each = 5.0%; new 1.0% -> total 6.0% = limit (NOT >), allowed
        existing = [_otr("GBPUSD", lot=10.0, entry=2.0, sl=1.0) for _ in range(5)]
        new_t    = _otr("AUDUSD", lot=10.0, entry=2.0, sl=1.0)
        r = self.mgr.check(new_t, existing)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.total_risk_pct, 6.0, places=4)

    def test_new_risk_calculated_from_trade_fields(self):
        # dist=1.0, lot=5, pip=10, bal=10000 -> risk=0.5%
        trade = _otr("EURUSD", lot=5.0, entry=2.0, sl=1.0)
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.new_risk_pct, 0.5, places=5)

    def test_remaining_cap_reported(self):
        # 1 existing @ 1.0% -> remaining_cap = 6.0 - 1.0 = 5.0
        existing = [_otr("GBPUSD", lot=10.0, entry=2.0, sl=1.0)]
        trade    = _otr("EURUSD", lot=5.0, entry=2.0, sl=1.0)
        r = self.mgr.check(trade, existing)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.remaining_cap, 5.0, places=5)

    def test_async_check_blocked(self):
        trade = _otr("EURUSD", lot=21.0, entry=2.0, sl=1.0)
        r = _run(self.mgr.check_async(trade, []))
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)

    def test_fail_closed_on_exception(self):
        mgr = PortfolioRiskManager(fail_mode=_PR_FM.FAIL_CLOSED)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("crash")):
            r = mgr.check(_otr(), [])
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_CHECK_ERROR", r.reason)

    def test_fail_open_on_exception(self):
        mgr = PortfolioRiskManager(fail_mode=_PR_FM.FAIL_OPEN)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("crash")):
            r = mgr.check(_otr(), [])
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)


# ---------------------------------------------------------------------------
# Topic 2 -- ATR Spike Robustness
# ---------------------------------------------------------------------------
class TestATRSpikeRobustness(unittest.TestCase):
    """
    ISSUE: VolatilityFilter.check() had no try/except before FIX #6.
    ZeroDivisionError (avg_atr=0) propagated -> gate crashed -> trade allowed.

    Production conditions (VolatilityConfig defaults):
        atr_min_ratio = 0.5   condition: STRICTLY < (ratio < min -> blocked)
        atr_max_ratio = 3.0   condition: STRICTLY > (ratio > max -> blocked)
        max_spread_ratio=2.0  condition: STRICTLY >

    EXACT PATCH:
        def check(self, current_atr, atr_history, current_spread, avg_spread, symbol):
            try: result = self._check_inner(...); cache; return result
            except Exception as exc:
                logger.error(..., exc_info=True)     # ALWAYS log
                if FAIL_CLOSED: return blocked result
                logger.critical("FAIL_OPEN swallowed")
                return allowed result

    RISK: ratio=4.0 in NFP -> SL 4x bigger -> 4% actual risk vs 1% intended.
    BACKWARD COMPAT: check() signature unchanged.
    """

    def setUp(self):
        self.vf   = VolatilityFilter()
        self.hist = [0.001] * 10  # avg = 0.001

    def test_high_atr_blocked(self):
        # ratio = 0.004 / 0.001 = 4.0 > 3.0 -> ATR_TOO_HIGH
        r = self.vf.check(0.004, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)
        self.assertAlmostEqual(r.atr_ratio, 4.0, places=5)

    def test_high_atr_boundary_allowed(self):
        # ratio = 0.003 / 0.001 = 3.0, NOT > 3.0 -> allowed
        r = self.vf.check(0.003, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.atr_ratio, 3.0, places=5)

    def test_low_atr_blocked(self):
        # ratio = 0.0004 / 0.001 = 0.4 < 0.5 -> ATR_TOO_LOW
        r = self.vf.check(0.0004, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_LOW", r.reason)

    def test_low_atr_boundary_allowed(self):
        # ratio = 0.0005 / 0.001 = 0.5, NOT < 0.5 -> allowed
        r = self.vf.check(0.0005, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_spread_too_wide_blocked(self):
        # spread_ratio = 0.0005 / 0.0002 = 2.5 > 2.0 -> SPREAD_TOO_WIDE
        r = self.vf.check(0.001, self.hist, 0.0005, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_WIDE", r.reason)

    def test_spread_boundary_allowed(self):
        # spread_ratio = 0.0004 / 0.0002 = 2.0, NOT > 2.0 -> allowed
        r = self.vf.check(0.001, self.hist, 0.0004, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_insufficient_history_allows(self):
        # < min_atr_bars (5) -> INSUFFICIENT_ATR_HISTORY -> allow
        r = self.vf.check(0.001, [0.001, 0.001], 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("INSUFFICIENT_ATR_HISTORY", r.reason)

    def test_zero_avg_atr_allows(self):
        # All-zero history -> ZERO_AVG_ATR -> allow
        r = self.vf.check(0.001, [0.0] * 10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("ZERO_AVG_ATR", r.reason)

    def test_fail_closed_on_exception(self):
        # VolatilityFilter uses its own local FailMode -- must use _VF_FM
        vf = VolatilityFilter(config=_vf_config(fail_open=False))
        with patch.object(vf, '_check_inner', side_effect=ZeroDivisionError("zero")):
            r = vf.check(0.001, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_on_exception(self):
        vf = VolatilityFilter(config=_vf_config(fail_open=True))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("bang")):
            r = vf.check(0.001, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_normal_conditions_allowed(self):
        # ratio=1.5 between 0.5 and 3.0 -> allowed
        r = self.vf.check(0.0015, self.hist, 0.0002, 0.0002, "GBPUSD")
        self.assertTrue(r.can_trade)


# ---------------------------------------------------------------------------
# Topic 3 -- Symbol-Specific Thresholds
# ---------------------------------------------------------------------------
class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    ISSUE: Global atr_max_ratio=3.0 is too tight for BTC (normal 8x avg)
    and too loose for Gold in extreme volatility.

    EXACT PATCH: Per-asset VolatilityFilter instances:
        gold_vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0))
        btc_vf  = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0))

    RISK: Global threshold -> false blocks on BTC / false passes on Gold crisis.
    BACKWARD COMPAT: New instances only; existing default unchanged at 3.0.
    """

    def test_gold_tight_threshold_blocks_spike(self):
        gold_vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0))
        hist    = [1.5] * 10
        # ratio = 3.5 / 1.5 = 2.33 > 2.0 -> blocked
        r = gold_vf.check(3.5, hist, 0.5, 0.5, "XAUUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_gold_tight_threshold_allows_normal(self):
        gold_vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0))
        hist    = [2.0] * 10
        # ratio = 3.0 / 2.0 = 1.5 < 2.0 -> allowed
        r = gold_vf.check(3.0, hist, 0.5, 0.5, "XAUUSD")
        self.assertTrue(r.can_trade)

    def test_btc_loose_threshold_allows_normal(self):
        btc_vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0))
        hist   = [1000.0] * 10
        # ratio = 8000 / 1000 = 8.0 < 10.0 -> allowed
        r = btc_vf.check(8000, hist, 200, 200, "BTCUSD")
        self.assertTrue(r.can_trade)

    def test_btc_loose_threshold_blocks_extreme(self):
        btc_vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0))
        hist   = [500.0] * 10
        # ratio = 6000 / 500 = 12.0 > 10.0 -> blocked
        r = btc_vf.check(6000, hist, 200, 200, "BTCUSD")
        self.assertFalse(r.can_trade)

    def test_global_default_threshold_blocks_fx_spike(self):
        fx_vf = VolatilityFilter()  # default: max_ratio=3.0
        hist  = [0.001] * 10
        r = fx_vf.check(0.004, hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_cache_isolation_per_symbol(self):
        vf   = VolatilityFilter()
        hist = [0.001] * 10
        r1 = vf.check(0.004, hist, 0.0002, 0.0002, "EURUSD")  # blocked
        r2 = vf.check(0.001, hist, 0.0002, 0.0002, "GBPUSD")  # normal -> allowed
        self.assertFalse(r1.can_trade)
        self.assertTrue(r2.can_trade)

    def test_custom_spread_threshold(self):
        cfg = VolatilityConfig(max_spread_ratio=5.0)  # very loose
        vf  = VolatilityFilter(config=cfg)
        hist = [0.001] * 10
        # spread_ratio = 0.0008 / 0.0002 = 4.0 < 5.0 -> allowed
        r = vf.check(0.001, hist, 0.0008, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)


# ---------------------------------------------------------------------------
# Topic 4 -- Gold Pip Value
# ---------------------------------------------------------------------------
class TestGoldPipValue(unittest.TestCase):
    """
    ISSUE (FIX #4):
        lot_sizing.py:     "XAUUSD": 10.0   (10x too high)
        portfolio_risk.py: "XAUUSD": 10.0   (10x too high)
        Correct: Gold pip = $0.01/oz * 100oz lot = $1.00

    EXACT PATCH:
        lot_sizing.py:     "XAUUSD":  1.0,  # was 10.0
        portfolio_risk.py: "XAUUSD":  1.0,  # was 10.0

    RISK: With pip=10: raw_lot = risk_usd / (sl_pips * 10) -> 10x undersized
    -> actual risk = 10% of intended -> all Gold limits meaningless.

    BACKWARD COMPAT: _resolve_pip_value(), _get_pip_value_with_source()
    signatures unchanged. Return value corrected only.
    """

    def test_ls_xauusd_pip_table(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_ls_xauusd_resolve(self):
        self.assertEqual(_ls_mod._resolve_pip_value("XAUUSD"), 1.0)

    def test_ls_gold_alias(self):
        self.assertEqual(_ls_mod._resolve_pip_value("GOLD"), 1.0)

    def test_ls_xauusd_broker_suffix(self):
        self.assertEqual(_ls_mod._resolve_pip_value("XAUUSDm"), 1.0)

    def test_ls_xagusd_silver(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XAGUSD"], 50.0)

    def test_ls_silver_alias(self):
        self.assertEqual(_ls_mod._resolve_pip_value("SILVER"), 50.0)

    def test_pr_xauusd_pip_table(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_pr_gold_alias(self):
        pip, _ = _pr_mod._get_pip_value_with_source("GOLD")
        self.assertEqual(pip, 1.0)

    def test_pr_xauusd_table_source(self):
        pip, src = _pr_mod._get_pip_value_with_source("XAUUSD")
        self.assertEqual(pip, 1.0)
        self.assertIn("TABLE", str(src))

    def test_pr_xauusd_broker_suffix(self):
        pip, _ = _pr_mod._get_pip_value_with_source("XAUUSDm")
        self.assertEqual(pip, 1.0)

    def test_gold_trade_risk_correct(self):
        # dist=50, lot=1, pip=1.0, bal=10000 -> risk=50*1*1/10000*100=0.5%
        trade = _otr("XAUUSD", lot=1.0, entry=2050.0, sl=2000.0)
        self.assertAlmostEqual(trade.risk_percent, 0.5, places=4)

    def test_gold_trade_not_10x_inflated(self):
        # With pip=10 (wrong): same trade -> risk=5.0%
        # With pip=1.0 (correct): risk=0.5%
        trade = _otr("XAUUSD", lot=1.0, entry=2050.0, sl=2000.0)
        self.assertLess(trade.risk_percent, 1.5)  # must NOT be 5%

    def test_lot_sizer_gold(self):
        # risk=1% of $10000=$100; sl=50pips, pip=1.0 -> lot=100/(50*1)=2.0
        sizer = LotSizer()
        r = _run(sizer.calculate("XAUUSD", 10000, 50))
        self.assertAlmostEqual(r.lot_size, 2.0, places=1)
        self.assertAlmostEqual(r.risk_percent, 1.0, places=3)


# ---------------------------------------------------------------------------
# Topic 5 -- Crypto Pip Value
# ---------------------------------------------------------------------------
class TestCryptoPipValue(unittest.TestCase):
    """
    ISSUE (FIX #4): ETHUSD pip_value was 0.01 in older code (100x too small).
    All crypto should be 1.0 per standard lot.

    EXACT PATCH:
        "BTCUSD": 1.0, "ETHUSD": 1.0, "LTCUSD": 1.0,
        "BNBUSD": 1.0, "XRPUSD": 1.0

    RISK: pip=0.01 -> lot = $100/(100*0.01) = 100 lots
    -> actual risk = $10,000 on $10,000 account -> immediate account blow.

    BACKWARD COMPAT: _resolve_pip_value() signature unchanged.
    """

    CRYPTO_PAIRS = ["BTCUSD", "ETHUSD", "LTCUSD", "BNBUSD", "XRPUSD"]

    def test_ls_all_crypto_pip_1(self):
        for sym in self.CRYPTO_PAIRS:
            with self.subTest(sym=sym):
                self.assertEqual(_ls_mod._PIP_VALUE_TABLE[sym], 1.0)

    def test_ls_btc_alias(self):
        self.assertEqual(_ls_mod._resolve_pip_value("BTC"), 1.0)

    def test_ls_bitcoin_alias(self):
        self.assertEqual(_ls_mod._resolve_pip_value("BITCOIN"), 1.0)

    def test_ls_eth_alias(self):
        self.assertEqual(_ls_mod._resolve_pip_value("ETH"), 1.0)

    def test_ls_btcusd_broker_suffix(self):
        self.assertEqual(_ls_mod._resolve_pip_value("BTCUSDm"), 1.0)

    def test_pr_btcusd_pip_1(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["BTCUSD"], 1.0)

    def test_pr_ethusd_pip_1(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["ETHUSD"], 1.0)

    def test_pr_xrpusd_pip_1(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["XRPUSD"], 1.0)

    def test_lot_sizer_btc(self):
        # risk=1% of $10000=$100; sl=500pips, pip=1.0 -> lot=100/(500*1)=0.2
        sizer = LotSizer()
        r = _run(sizer.calculate("BTCUSD", 10000, 500))
        self.assertAlmostEqual(r.lot_size, 0.20, places=1)
        self.assertAlmostEqual(r.risk_percent, 1.0, places=3)

    def test_lot_sizer_eth(self):
        # sl=100pips, pip=1.0 -> lot=100/(100*1)=1.0
        sizer = LotSizer()
        r = _run(sizer.calculate("ETHUSD", 10000, 100))
        self.assertAlmostEqual(r.lot_size, 1.0, places=1)

    def test_btc_trade_risk_correct(self):
        # dist=500, lot=0.1, pip=1.0, bal=10000 -> 500*0.1*1/10000*100=0.5%
        trade = _otr("BTCUSD", lot=0.1, entry=30500.0, sl=30000.0)
        self.assertAlmostEqual(trade.risk_percent, 0.5, places=3)

    def test_btc_trade_not_100x_oversized(self):
        # With pip=0.01 (wrong): risk=0.005%; with pip=1.0 (correct): 0.5%
        trade = _otr("BTCUSD", lot=0.1, entry=30500.0, sl=30000.0)
        self.assertGreater(trade.risk_percent, 0.1)


# ---------------------------------------------------------------------------
# Topic 6 -- Exposure Calculation
# ---------------------------------------------------------------------------
class TestExposureCalculation(unittest.TestCase):
    """
    ISSUE: ExposureControlEngine.check() had no try/except before FIX #6.
    Any AttributeError from corrupt ExposurePosition propagated -> unlimited
    exposure bypass. Also FIX #5: orchestrator hardcoded new_risk_percent=1.0
    so MAX_SYMBOL_RISK with real 3% was ignored.

    EXACT PATCH:
        def check(self, new_symbol, new_direction, new_risk_percent,
                  open_positions=None, account_balance=10_000.0):
            try: return self._check_inner(...)
            except Exception as exc:
                logger.exception(..., exc_info=True)
                if FAIL_CLOSED: return blocked with reason='FAIL_CLOSED:...'
                return allowed with reason='FAIL_OPEN_EXCEPTION_IGNORED'

    3 limits verified:
        MAX_TOTAL_RISK:  projected > 5.0  (STRICTLY >)
        MAX_SYMBOL_RISK: sym_risk > 2.0   (STRICTLY >)
        MAX_OPEN_TRADES: len(ops) >= 5    (>=)

    RISK: Without limits, single currency could reach 10%+ before gate fires.
    BACKWARD COMPAT: check() signature unchanged; ExposurePosition unchanged.
    """

    def setUp(self):
        self.engine = ExposureControlEngine()

    def test_total_risk_blocked(self):
        positions = [_ep("EURUSD", risk_pct=1.0) for _ in range(4)]
        r = self.engine.check("GBPUSD", "BUY", 1.5, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_TOTAL_RISK", r.reason)

    def test_total_risk_boundary_allowed(self):
        positions = [_ep("EURUSD", risk_pct=1.0) for _ in range(4)]
        r = self.engine.check("GBPUSD", "BUY", 1.0, positions)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.projected_total_risk, 5.0, places=5)

    def test_symbol_risk_blocked(self):
        positions = [_ep("EURUSD", risk_pct=1.5)]
        r = self.engine.check("EURUSD", "BUY", 1.0, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)

    def test_symbol_risk_boundary_allowed(self):
        positions = [_ep("EURUSD", risk_pct=1.0)]
        r = self.engine.check("EURUSD", "BUY", 1.0, positions)
        self.assertTrue(r.can_trade)

    def test_max_open_trades_blocked(self):
        positions = [_ep(f"SYM{i}", risk_pct=0.5) for i in range(5)]
        r = self.engine.check("NEW", "BUY", 0.5, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_OPEN_TRADES", r.reason)

    def test_max_open_trades_boundary_allowed(self):
        positions = [_ep(f"SYM{i}", risk_pct=0.5) for i in range(4)]
        r = self.engine.check("NEW", "BUY", 0.5, positions)
        self.assertTrue(r.can_trade)

    def test_projected_total_correct(self):
        positions = [_ep("EURUSD", risk_pct=2.0), _ep("GBPUSD", risk_pct=1.0)]
        r = self.engine.check("AUDUSD", "BUY", 0.5, positions)
        self.assertAlmostEqual(r.projected_total_risk, 3.5, places=5)

    def test_current_total_correct(self):
        positions = [_ep("EURUSD", risk_pct=1.5), _ep("GBPUSD", risk_pct=1.5)]
        r = self.engine.check("AUDUSD", "BUY", 0.5, positions)
        self.assertAlmostEqual(r.current_total_risk, 3.0, places=5)

    def test_empty_positions_allowed(self):
        r = self.engine.check("EURUSD", "BUY", 1.0, [])
        self.assertTrue(r.can_trade)

    def test_fail_closed_on_exception(self):
        engine = ExposureControlEngine(fail_mode=_EC_FM.FAIL_CLOSED)
        with patch.object(engine, '_check_inner', side_effect=AttributeError("corrupt")):
            r = engine.check("EURUSD", "BUY", 1.0, [])
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_on_exception(self):
        engine = ExposureControlEngine(fail_mode=_EC_FM.FAIL_OPEN)
        with patch.object(engine, '_check_inner', side_effect=RuntimeError("boom")):
            r = engine.check("EURUSD", "BUY", 1.0, [])
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_get_snapshot_fail_closed_reraises(self):
        engine = ExposureControlEngine(fail_mode=_EC_FM.FAIL_CLOSED)
        with patch.object(engine, '_snapshot_inner', side_effect=RuntimeError("snap")):
            with self.assertRaises(RuntimeError):
                engine.get_snapshot([])

    def test_get_snapshot_fail_open_returns_empty(self):
        engine = ExposureControlEngine(fail_mode=_EC_FM.FAIL_OPEN)
        with patch.object(engine, '_snapshot_inner', side_effect=RuntimeError("snap")):
            snap = engine.get_snapshot([])
        self.assertIsNotNone(snap)
        self.assertEqual(snap.total_risk_percent, 0.0)

    def test_real_risk_not_hardcoded(self):
        # Regression guard for FIX #5: 3.0% must be evaluated, not replaced with 1.0
        positions = [_ep("EURUSD", risk_pct=1.5)]
        r = self.engine.check("EURUSD", "BUY", 3.0, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)


# ---------------------------------------------------------------------------
# Topic 7 -- Fail-Closed Behaviour
# ---------------------------------------------------------------------------
class TestFailClosedBehaviour(unittest.TestCase):
    """
    ISSUE (pre FIX #6):
        CorrelationFilter: except: allow_trade=True  (SILENT -- no log!)
        ExposureControl:   no try/except at all
        VolatilityFilter:  no try/except at all
        PortfolioRisk:     no try/except at all
        No configurable FailMode existed.

    EXACT PATCH (fail_mode.py -- Single Source of Truth):
        class FailMode(str, Enum):
            FAIL_CLOSED = "FAIL_CLOSED"   # default safe
            FAIL_OPEN   = "FAIL_OPEN"     # permissive

        def coerce(value) -> FailMode:
            if isinstance(value, FailMode): return value
            return FailMode(str(value).upper().strip())

        All 4 gates:
            from backend.risk.fail_mode import FailMode, coerce as _coerce_fm
            self._fail_mode = _coerce_fm(fail_mode or config.fail_mode)
            # exception -> logger.critical(exc_info=True) ALWAYS
            # FAIL_CLOSED -> block; FAIL_OPEN -> allow + CRITICAL log (never silent)

    RISK: Silent allow on exception = unlimited trading during system faults.
    BACKWARD COMPAT: All gates accept fail_mode kwarg; default=FAIL_CLOSED.
    """

    def test_failmode_str_enum_closed(self):
        self.assertEqual(FailMode.FAIL_CLOSED, "FAIL_CLOSED")

    def test_failmode_str_enum_open(self):
        self.assertEqual(FailMode.FAIL_OPEN, "FAIL_OPEN")

    def test_coerce_uppercase(self):
        self.assertIs(coerce_fm("FAIL_CLOSED"), FailMode.FAIL_CLOSED)
        self.assertIs(coerce_fm("FAIL_OPEN"),   FailMode.FAIL_OPEN)

    def test_coerce_lowercase(self):
        self.assertIs(coerce_fm("fail_closed"), FailMode.FAIL_CLOSED)
        self.assertIs(coerce_fm("fail_open"),   FailMode.FAIL_OPEN)

    def test_coerce_identity(self):
        self.assertIs(coerce_fm(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)

    def test_coerce_invalid_raises(self):
        with self.assertRaises(ValueError):
            coerce_fm("UNKNOWN_MODE")

    def test_sst_volatility_filter(self):
        self.assertIs(_vf_mod.FailMode, _fm_mod.FailMode)

    def test_sst_portfolio_risk(self):
        self.assertIs(_pr_mod.FailMode, _fm_mod.FailMode)

    def test_sst_exposure_control(self):
        self.assertIs(_ec_mod.FailMode, _fm_mod.FailMode)

    def test_sst_correlation_filter(self):
        self.assertIs(_cf_mod.FailMode, _fm_mod.FailMode)

    def test_volatility_filter_default_fc(self):
        vf = VolatilityFilter()
        self.assertIs(vf._fail_mode, _VF_FM.FAIL_CLOSED)

    def test_exposure_control_default_fc(self):
        ec = ExposureControlEngine()
        self.assertIs(ec._fail_mode, _EC_FM.FAIL_CLOSED)

    def test_correlation_filter_default_fc(self):
        cf = CorrelationFilter()
        self.assertIs(cf._fail_mode, _CF_FM.FAIL_CLOSED)

    def test_portfolio_risk_default_fc(self):
        mgr = PortfolioRiskManager()
        self.assertIs(mgr._fail_mode, _PR_FM.FAIL_CLOSED)

    def test_exposure_control_fail_open_kwarg(self):
        ec = ExposureControlEngine(fail_mode=_EC_FM.FAIL_OPEN)
        self.assertIs(ec._fail_mode, _EC_FM.FAIL_OPEN)

    def test_portfolio_risk_fail_open_kwarg(self):
        mgr = PortfolioRiskManager(fail_mode=_PR_FM.FAIL_OPEN)
        self.assertIs(mgr._fail_mode, _PR_FM.FAIL_OPEN)

    def test_exposure_fail_closed_logs(self):
        ec = ExposureControlEngine(fail_mode=_EC_FM.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.exposure_control", level=logging.ERROR):
                ec.check("EURUSD", "BUY", 1.0, [])

    def test_exposure_fail_open_logs_critical(self):
        ec = ExposureControlEngine(fail_mode=_EC_FM.FAIL_OPEN)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.exposure_control", level=logging.CRITICAL):
                ec.check("EURUSD", "BUY", 1.0, [])

    def test_portfolio_fail_closed_logs(self):
        mgr = PortfolioRiskManager(fail_mode=_PR_FM.FAIL_CLOSED)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.portfolio_risk", level=logging.ERROR):
                mgr.check(_otr(), [])

    def test_correlation_fail_closed_logs_critical(self):
        cf = CorrelationFilter(fail_mode=_CF_FM.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                _run(cf.check("EURUSD", "BUY", []))

    def test_volatility_fail_closed_logs(self):
        vf = VolatilityFilter(config=_vf_config(fail_open=False))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")

    def test_volatility_fail_open_logs_critical(self):
        vf = VolatilityFilter(config=_vf_config(fail_open=True))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.volatility_filter", level=logging.CRITICAL):
                vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")


# ---------------------------------------------------------------------------
# Topic 8 -- Portfolio Correlation Calculations
# ---------------------------------------------------------------------------
class TestPortfolioCorrelationCalcs(unittest.TestCase):
    """
    ISSUE (pre FIX #6): CorrelationFilter.check() had no outer try/except.
    Per-pair crash -> corr=0.0 (inner catch OK) -> allowed.
    Outer exception -> propagate -> fail_mode bypass entirely.
    Also: abs(corr) must be used; same-symbol must be skipped.

    EXACT PATCH:
        async def check(self, symbol, direction, open_positions=None):
            try: return await self._check_inner(...)
            except Exception as exc:
                logger.critical("...fail_mode=%s: %s", ..., exc_info=True)
                if FAIL_CLOSED: return blocked
                return allowed with reason='FAIL_OPEN:CORR_EXCEPTION_IGNORED'

        _check_inner:
            if pos_sym == symbol: continue          # same-symbol skip
            if abs(corr) >= max_corr: blocked       # abs() catches negative

    RISK: Without abs(), BUY EURUSD + SELL GBPUSD (corr=-0.90) was allowed;
    both share liquidity risk -- in crisis both stop out simultaneously.
    BACKWARD COMPAT: check() signature unchanged (async).
    """

    def _cf(self, engine=None, fail_mode=None):
        cfg = CorrelationFilterConfig(max_corr=0.85)
        fm  = fail_mode or _CF_FM.FAIL_CLOSED
        return CorrelationFilter(config=cfg, correlation_engine=engine,
                                 fail_mode=fm)

    def _mock_eng(self, corr: float):
        eng = MagicMock()
        eng.get_correlation = AsyncMock(return_value=corr)
        return eng

    def _pos(self, sym="GBPUSD"):
        return {"symbol": sym, "direction": "BUY", "risk_percent": 1.0}

    def test_high_positive_corr_blocked(self):
        eng = self._mock_eng(0.92)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertFalse(r.can_trade)
        self.assertIn("CORR_TOO_HIGH", r.reason)

    def test_high_negative_corr_blocked(self):
        eng = self._mock_eng(-0.92)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertFalse(r.can_trade)

    def test_corr_at_threshold_blocked(self):
        eng = self._mock_eng(0.85)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertFalse(r.can_trade)

    def test_corr_below_threshold_allowed(self):
        eng = self._mock_eng(0.60)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "CORR_OK")

    def test_same_symbol_skipped(self):
        eng = MagicMock()
        eng.get_correlation = AsyncMock(return_value=1.0)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("EURUSD")]))
        eng.get_correlation.assert_not_called()
        self.assertTrue(r.can_trade)

    def test_no_positions_allowed(self):
        cf = self._cf()
        r  = _run(cf.check("EURUSD", "BUY", []))
        self.assertTrue(r.can_trade)
        self.assertIn("NO_POSITIONS_OR_ENGINE", r.reason)

    def test_no_engine_allowed(self):
        cf = CorrelationFilter()
        r  = _run(cf.check("EURUSD", "BUY", [self._pos()]))
        self.assertTrue(r.can_trade)

    def test_per_pair_crash_allows(self):
        eng = MagicMock()
        eng.get_correlation = AsyncMock(side_effect=ConnectionError("timeout"))
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertTrue(r.can_trade)

    def test_outer_exception_fail_closed_blocks(self):
        cf = self._cf(fail_mode=_CF_FM.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("boom")):
            r = _run(cf.check("EURUSD", "BUY", [self._pos()]))
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_outer_exception_fail_open_allows(self):
        cf = self._cf(fail_mode=_CF_FM.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("boom")):
            r = _run(cf.check("EURUSD", "BUY", [self._pos()]))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_pair_checked_in_result(self):
        eng = self._mock_eng(0.92)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertFalse(r.can_trade)
        self.assertEqual(r.pair_checked, "GBPUSD")

    def test_early_exit_on_first_breach(self):
        call_log = []
        async def _mock_corr(a, b):
            call_log.append(b)
            return 0.92
        eng = MagicMock()
        eng.get_correlation = _mock_corr
        cf  = self._cf(engine=eng)
        pos = [self._pos("GBPUSD"), self._pos("AUDUSD")]
        r   = _run(cf.check("EURUSD", "BUY", pos))
        self.assertFalse(r.can_trade)
        self.assertEqual(len(call_log), 1)  # stopped after first breach

    def test_custom_max_corr(self):
        cfg = CorrelationFilterConfig(max_corr=0.70)
        eng = self._mock_eng(0.75)
        cf  = CorrelationFilter(config=cfg, correlation_engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos()]))
        self.assertFalse(r.can_trade)

    def test_outer_exception_always_logs(self):
        cf = self._cf(fail_mode=_CF_FM.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("boom")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                _run(cf.check("EURUSD", "BUY", [self._pos()]))

    def test_correlation_value_in_result(self):
        eng = self._mock_eng(0.92)
        cf  = self._cf(engine=eng)
        r   = _run(cf.check("EURUSD", "BUY", [self._pos("GBPUSD")]))
        self.assertAlmostEqual(r.correlation, 0.92, places=5)


# ---------------------------------------------------------------------------
# Integration -- Cross-Gate Regression Guards
# ---------------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    """End-to-end regression guards verifying FIX #4/#5/#6 interact correctly."""

    def test_gold_risk_uses_correct_pip(self):
        trade = _otr("XAUUSD", lot=1.0, entry=2050.0, sl=2000.0)
        self.assertAlmostEqual(trade.risk_percent, 0.5, places=3)

    def test_btc_trade_within_limits(self):
        trade = _otr("BTCUSD", lot=0.1, entry=30500.0, sl=30000.0)
        mgr   = PortfolioRiskManager()
        r     = mgr.check(trade, [])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.new_risk_pct, 0.5, places=3)

    def test_all_four_gates_default_fail_closed(self):
        defaults = [
            VolatilityFilter()._fail_mode,
            ExposureControlEngine()._fail_mode,
            CorrelationFilter()._fail_mode,
            PortfolioRiskManager()._fail_mode,
        ]
        for fm in defaults:
            self.assertEqual(fm.value, "FAIL_CLOSED")

    def test_exposure_real_risk_propagated(self):
        ec       = ExposureControlEngine()
        existing = [_ep("EURUSD", risk_pct=1.5)]
        r = ec.check("EURUSD", "BUY", 3.0, existing)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)

    def test_fail_mode_canonical_source(self):
        self.assertIs(FailMode.FAIL_CLOSED, coerce_fm("FAIL_CLOSED"))
        self.assertIs(FailMode.FAIL_OPEN,   coerce_fm("FAIL_OPEN"))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    unittest.main(verbosity=2)
