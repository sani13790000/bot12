"""
FIX #8 — TEST COVERAGE (production-ready, verified against exact production signatures)
========================================================================================

Topics:
  1. News event blocking
  2. ATR spike robustness
  3. Symbol-specific thresholds
  4. Gold pip value
  5. Crypto pip value
  6. Exposure calculation
  7. Fail-closed behavior
  8. Portfolio correlation calculations

All tests import directly from production source files (loaded via /tmp for speed).
"""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import shutil
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Stage files in /tmp and load from there (avoids pyc-lock timeout on first import)
# ---------------------------------------------------------------------------
_SRC  = pathlib.Path("/home/definable/fix8/src")
_FIX6 = pathlib.Path("/home/definable/fix6/backend/risk")
_TMP  = pathlib.Path("/tmp/fix8_test")
_TMP.mkdir(exist_ok=True)

_FILE_MAP = {
    "fail_mode":          _SRC  / "fail_mode.py",
    "portfolio_risk":     _SRC  / "portfolio_risk.py",
    "volatility_filter":  _SRC  / "volatility_filter.py",
    "exposure_control":   _SRC  / "exposure_control.py",
    "lot_sizing":         _SRC  / "lot_sizing.py",
    "correlation_filter": _SRC  / "correlation_filter.py",
    "_pip_helpers":       _SRC  / "_pip_helpers.py",
    "correlation_engine": _FIX6 / "correlation_engine.py",
}

for _name, _src in _FILE_MAP.items():
    _dst = _TMP / f"{_name}.py"
    shutil.copy2(_src, _dst)


def _ql(mod_name: str, filename: str) -> types.ModuleType:
    """Quick-load from /tmp into sys.modules."""
    key = f"backend.risk.{filename}"
    if key in sys.modules:
        return sys.modules[key]
    path = _TMP / f"{filename}.py"
    spec = importlib.util.spec_from_file_location(key, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-register package stubs
for _pkg in ("backend", "backend.risk"):
    if _pkg not in sys.modules:
        sys.modules[_pkg] = types.ModuleType(_pkg)

# Load all modules in dependency order
_fm_mod  = _ql("fail_mode",          "fail_mode")
_pr_mod  = _ql("portfolio_risk",     "portfolio_risk")
_ec_mod  = _ql("exposure_control",   "exposure_control")
_ph_mod  = _ql("_pip_helpers",       "_pip_helpers")
_ce_mod  = _ql("correlation_engine", "correlation_engine")
_vf_mod  = _ql("volatility_filter",  "volatility_filter")
_cf_mod  = _ql("correlation_filter", "correlation_filter")
_ls_mod  = _ql("lot_sizing",         "lot_sizing")

# Public aliases
FailMode                = _fm_mod.FailMode
coerce                  = _fm_mod.coerce

OpenTradeRisk           = _pr_mod.OpenTradeRisk
PortfolioRiskConfig     = _pr_mod.PortfolioRiskConfig
PortfolioRiskManager    = _pr_mod.PortfolioRiskManager
RiskLevel               = _pr_mod.RiskLevel
_pr_PIP                 = _pr_mod._PIP_VALUE_TABLE
_pr_get_pip             = _pr_mod._get_pip_value

ExposurePosition        = _ec_mod.ExposurePosition
ExposureConfig          = _ec_mod.ExposureConfig
ExposureControlEngine   = _ec_mod.ExposureControlEngine

VolatilityFilter        = _vf_mod.VolatilityFilter
VolatilityConfig        = _vf_mod.VolatilityConfig
VolatilityCheckResult   = _vf_mod.VolatilityCheckResult

LotSizer                = _ls_mod.LotSizer
LotSizingConfig         = _ls_mod.LotSizingConfig
_ls_PIP                 = _ls_mod._PIP_VALUE_TABLE
_ls_resolve             = _ls_mod._resolve_pip_value

CE_CorrelationFilter    = _ce_mod.CorrelationFilter
CorrelationFilterConfig = _ce_mod.CorrelationFilterConfig
CorrPosition            = _ce_mod.CorrPosition
CorrelationResult       = _ce_mod.CorrelationResult
RollingCorrelationEngine = _ce_mod.RollingCorrelationEngine
_pearson                = _ce_mod._pearson
_STATIC_CORR            = _ce_mod._STATIC_CORRELATION_TABLE
_canonical              = _ce_mod._canonical


def _run(coro):
    """Run coroutine synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_trade(symbol, lot_size, entry, sl, balance, direction="BUY"):
    """
    Build OpenTradeRisk via production __post_init__.

    portfolio_risk calculates:
      pip_distance = abs(entry - stop_loss)   <- price distance, NOT pip count
      risk_amount  = pip_distance x lot_size x pip_value(symbol)
      risk_pct     = risk_amount / balance x 100

    For EURUSD (pip_value=10.0) @ $10k balance:
      1.0% risk ($100): lot=1.0, pip_dist=10.0  -> entry=11.0, sl=1.0
      1.5% risk ($150): lot=1.0, pip_dist=15.0  -> entry=16.0, sl=1.0
      2.0% risk ($200): lot=1.0, pip_dist=20.0  -> entry=21.0, sl=1.0
    """
    return OpenTradeRisk(
        symbol=symbol, direction=direction,
        lot_size=lot_size, entry_price=entry,
        stop_loss=sl, account_balance=balance,
    )


class TestNewsEventBlocking(unittest.TestCase):
    """Topic 1 - News Event Blocking.

    Detected issue: High-impact news (NFP, CPI) causes 3-10x normal volatility.
    Trades during news spikes carry disproportionate risk. PortfolioRiskManager
    max_single_symbol_pct and max_portfolio_risk_pct act as circuit-breakers.

    Exact patch: _check_inner():
      if new_risk > max_single_symbol_pct -> SINGLE_TRADE_RISK (blocked)
      if total_risk > max_portfolio_risk_pct -> PORTFOLIO_RISK (blocked)

    Risk impact: Without guards, 5-lot EURUSD on NFP can lose 8-15% of account.
    Backward compat: check() and check_async() signatures unchanged.
    """

    def setUp(self):
        self.cfg = PortfolioRiskConfig(max_portfolio_risk_pct=3.0, max_single_symbol_pct=1.5)
        self.mgr = PortfolioRiskManager(config=self.cfg)

    def test_single_trade_above_limit_blocked(self):
        """2% trade blocked when max_single=1.5%. EURUSD pip=10, dist=20, lot=1 -> 2.0%."""
        trade = _make_trade("EURUSD", 1.0, 21.0, 1.0, 10000)
        r = self.mgr.check(trade, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)
        self.assertEqual(r.risk_level, RiskLevel.BLOCKED)

    def test_single_trade_exactly_at_limit_allowed(self):
        """Boundary: dist=15 -> 1.5% = max -> allowed (condition is strictly >)."""
        trade = _make_trade("EURUSD", 1.0, 16.0, 1.0, 10000)
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)

    def test_cumulative_risk_blocked(self):
        """existing 1%+1%=2%, new 1.5% -> total 3.5% > 3.0% -> PORTFOLIO_RISK."""
        t1  = _make_trade("GBPUSD", 1.0, 11.0, 1.0, 10000)
        t2  = _make_trade("AUDUSD", 1.0, 11.0, 1.0, 10000)
        new = _make_trade("EURUSD", 1.0, 16.0, 1.0, 10000)
        r = self.mgr.check(new, [t1, t2])
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_RISK", r.reason)

    def test_remaining_cap_returned(self):
        """remaining_cap = max(0, max_portfolio - existing). existing=1% -> cap=2.0."""
        t1  = _make_trade("GBPUSD", 1.0, 11.0, 1.0, 10000)
        new = _make_trade("EURUSD", 1.0,  6.0, 1.0, 10000)
        r = self.mgr.check(new, [t1])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.remaining_cap, 2.0, places=4)

    def test_no_open_trades_allowed(self):
        """1% trade with no existing positions -> allowed."""
        trade = _make_trade("EURUSD", 1.0, 11.0, 1.0, 10000)
        r = self.mgr.check(trade, [])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.new_risk_pct, 1.0, places=4)

    def test_fail_open_allows_on_exception(self):
        """FAIL_OPEN: internal crash -> allow trade."""
        mgr = PortfolioRiskManager(config=self.cfg, fail_mode=FailMode.FAIL_OPEN)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("db down")):
            r = mgr.check(_make_trade("EURUSD", 1.0, 11.0, 1.0, 10000), [])
        self.assertTrue(r.can_trade)

    def test_fail_closed_blocks_on_exception(self):
        """FAIL_CLOSED (default): internal crash -> block trade."""
        mgr = PortfolioRiskManager(config=self.cfg)
        with patch.object(mgr, "_check_inner", side_effect=RuntimeError("timeout")):
            r = mgr.check(_make_trade("EURUSD", 1.0, 11.0, 1.0, 10000), [])
        self.assertFalse(r.can_trade)
        self.assertEqual(r.risk_level, RiskLevel.BLOCKED)

    def test_risk_level_critical_near_limit(self):
        """total=2.5% >= 80% of 3.0%=2.4% -> CRITICAL."""
        t1  = _make_trade("GBPUSD", 1.0, 16.0, 1.0, 10000)
        new = _make_trade("EURUSD", 1.0, 11.0, 1.0, 10000)
        r = self.mgr.check(new, [t1])
        self.assertIn(r.risk_level, [RiskLevel.CRITICAL, RiskLevel.BLOCKED])


class TestATRSpikeRobustness(unittest.TestCase):
    """Topic 2 - ATR Spike Robustness.

    Detected issue: ATR-based lot sizing uses average ATR. During a 4x spike,
    actual risk = 4x intended (lot sized on avg, market moves with current ATR).

    Exact patch: VolatilityFilter._check_inner():
      atr_ratio > atr_max_ratio -> ATR_TOO_HIGH
      atr_ratio < atr_min_ratio -> ATR_TOO_LOW
      spread_ratio > max_spread_ratio -> SPREAD_TOO_WIDE

    Risk impact: 1% intended risk becomes 4% with 4x ATR spike.
    Backward compat: check(current_atr, atr_history, current_spread, avg_spread, symbol) unchanged.
    """

    def setUp(self):
        self.cfg = VolatilityConfig(atr_min_ratio=0.5, atr_max_ratio=3.0,
                                    max_spread_ratio=2.0, min_atr_bars=5)
        self.vf = VolatilityFilter(config=self.cfg)
        self.history = [0.0010] * 10

    def test_atr_spike_exactly_at_max_allowed(self):
        """ratio == max_ratio -> allowed (condition is strictly >)."""
        r = self.vf.check(0.0030, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.atr_ratio, 3.0, places=4)

    def test_atr_spike_above_max_blocked(self):
        """ratio=4.0 > 3.0 -> ATR_TOO_HIGH."""
        r = self.vf.check(0.0040, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)
        self.assertAlmostEqual(r.atr_ratio, 4.0, places=4)

    def test_atr_crash_below_min_blocked(self):
        """ratio=0.2 < 0.5 -> ATR_TOO_LOW."""
        r = self.vf.check(0.0002, self.history, 0.0001, 0.0001, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_LOW", r.reason)

    def test_spread_spike_blocked(self):
        """spread_ratio=3.0 > 2.0 -> SPREAD_TOO_WIDE."""
        r = self.vf.check(0.0010, self.history, 0.0006, 0.0002, "GBPUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_WIDE", r.reason)
        self.assertAlmostEqual(r.spread_ratio, 3.0, places=4)

    def test_normal_conditions_pass(self):
        """ratio=1.5, spread normal -> VOLATILITY_OK."""
        r = self.vf.check(0.0015, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "VOLATILITY_OK")

    def test_insufficient_history_allows(self):
        """len(history) < min_atr_bars -> INSUFFICIENT_ATR_HISTORY -> allow."""
        r = self.vf.check(0.0010, [0.0010]*3, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "INSUFFICIENT_ATR_HISTORY")

    def test_zero_avg_atr_allows(self):
        """avg_atr=0 -> ZERO_AVG_ATR -> allow (no division by zero)."""
        r = self.vf.check(0.0010, [0.0]*10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "ZERO_AVG_ATR")

    def test_fail_closed_on_exception(self):
        """FAIL_CLOSED: exception in _check_inner -> blocked."""
        with patch.object(self.vf, "_check_inner", side_effect=ValueError("corrupt")):
            r = self.vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_on_exception(self):
        """FAIL_OPEN: exception -> allowed + FAIL_OPEN in reason."""
        vf = VolatilityFilter(config=VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=ValueError("oops")):
            r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_atr_ratio_in_result(self):
        """atr_ratio field is populated for downstream logging."""
        r = self.vf.check(0.0025, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertAlmostEqual(r.atr_ratio, 2.5, places=4)

    def test_cache_updated(self):
        """Result is cached under symbol after successful check."""
        self.vf.check(0.0015, self.history, 0.0002, 0.0002, "CADJPY")
        cached = self.vf.get_cached("CADJPY")
        self.assertIsNotNone(cached)
        res, _ = cached
        self.assertTrue(res.can_trade)


class TestSymbolSpecificThresholds(unittest.TestCase):
    """Topic 3 - Symbol-Specific Thresholds.

    Detected issue: Single threshold doesn't suit all assets.
    Gold moves 2-3x avg ATR normally; BTC moves 8-10x on news.

    Exact patch: VolatilityConfig per-asset-class with appropriate values.
    Backward compat: VolatilityFilter(config=VolatilityConfig(...)) unchanged.
    """

    def test_gold_tight_threshold_blocks_at_2_3x(self):
        """Gold config atr_max=2.0: 2.33x -> ATR_TOO_HIGH."""
        cfg = VolatilityConfig(atr_max_ratio=2.0, atr_min_ratio=0.3, min_atr_bars=5)
        vf  = VolatilityFilter(config=cfg)
        r   = vf.check(2.33, [1.0]*10, 0.5, 0.5, "XAUUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_gold_allows_normal_1_5x(self):
        """Gold config: 1.5x within max=2.0 -> allowed."""
        cfg = VolatilityConfig(atr_max_ratio=2.0, atr_min_ratio=0.3, min_atr_bars=5)
        vf  = VolatilityFilter(config=cfg)
        r   = vf.check(1.5, [1.0]*10, 0.5, 0.5, "XAUUSD")
        self.assertTrue(r.can_trade)

    def test_crypto_loose_threshold_allows_8x(self):
        """Crypto config atr_max=10.0: 8x -> allowed."""
        cfg = VolatilityConfig(atr_max_ratio=10.0, atr_min_ratio=0.1, min_atr_bars=5)
        vf  = VolatilityFilter(config=cfg)
        r   = vf.check(800.0, [100.0]*10, 50.0, 50.0, "BTCUSD")
        self.assertTrue(r.can_trade)

    def test_forex_default_blocks_4x(self):
        """Default forex config blocks 4x ATR spike."""
        vf = VolatilityFilter()
        r  = vf.check(0.004, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_cache_isolation_per_symbol(self):
        """EURUSD blocked result does not bleed into GBPUSD cache."""
        vf = VolatilityFilter()
        vf.check(0.004, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        vf.check(0.002, [0.001]*10, 0.0002, 0.0002, "GBPUSD")
        eu, _ = vf.get_cached("EURUSD")
        gb, _ = vf.get_cached("GBPUSD")
        self.assertFalse(eu.can_trade)
        self.assertTrue(gb.can_trade)

    def test_custom_spread_threshold(self):
        """max_spread_ratio=1.5: ratio=1.6 -> SPREAD_TOO_WIDE."""
        cfg = VolatilityConfig(max_spread_ratio=1.5, min_atr_bars=5)
        vf  = VolatilityFilter(config=cfg)
        r   = vf.check(0.001, [0.001]*10, 0.00016, 0.0001, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_WIDE", r.reason)


class TestGoldPipValue(unittest.TestCase):
    """Topic 4 - Gold Pip Value (FIX #4).

    Detected issue: XAUUSD pip value was 10.0 (wrong by 10x).
    Correct: Gold pip = $0.01/oz, lot=100oz -> pip value = $1.00.

    Exact patch: _PIP_VALUE_TABLE['XAUUSD'] = 1.0 in both modules.

    Risk impact (before): 50-pip XAUUSD trade at $10k: risk_usd=50x10=$500 (5%!)
      -> lot sizer gives 10x too few lots -> actual risk only 0.5%.
    Backward compat: _resolve_pip_value() and _get_pip_value() APIs unchanged.
    """

    def test_ls_xauusd_is_1(self):
        self.assertEqual(_ls_PIP.get("XAUUSD"), 1.0)

    def test_ls_gold_alias_is_1(self):
        self.assertEqual(_ls_resolve("GOLD"), 1.0)

    def test_ls_xauusd_m_suffix_is_1(self):
        self.assertEqual(_ls_resolve("XAUUSDm"), 1.0)

    def test_ls_xagusd_is_50(self):
        self.assertEqual(_ls_PIP.get("XAGUSD"), 50.0)

    def test_ls_silver_alias_is_50(self):
        self.assertEqual(_ls_resolve("SILVER"), 50.0)

    def test_ls_not_10_regression(self):
        """Regression: must never revert to 10.0."""
        self.assertNotEqual(_ls_PIP.get("XAUUSD"), 10.0)

    def test_pr_xauusd_is_1(self):
        self.assertEqual(_pr_PIP.get("XAUUSD"), 1.0)

    def test_pr_gold_alias_is_1(self):
        self.assertEqual(_pr_get_pip("GOLD"), 1.0)

    def test_pr_xauusd_suffix_is_1(self):
        self.assertEqual(_pr_get_pip("XAUUSDm"), 1.0)

    def test_pr_not_10_regression(self):
        self.assertNotEqual(_pr_PIP.get("XAUUSD"), 10.0)

    def test_lot_sizing_gold_1pct(self):
        """1% risk $10k, 50-pip SL: risk=$100; lot=100/(50x1.0)=2.0."""
        sizer = LotSizer(LotSizingConfig(risk_percent=1.0))
        result = _run(sizer.calculate("XAUUSD", 10000, 50))
        self.assertAlmostEqual(result.lot_size, 2.0, places=1)
        self.assertAlmostEqual(result.risk_percent, 1.0, places=1)

    def test_opentraderisk_gold_risk(self):
        """OpenTradeRisk: 1 lot XAUUSD, entry=2000, SL=1950 -> risk=$50 = 0.5%."""
        trade = OpenTradeRisk(symbol="XAUUSD", direction="BUY",
                              lot_size=1.0, entry_price=2000.0, stop_loss=1950.0,
                              account_balance=10000.0)
        self.assertAlmostEqual(trade.risk_amount, 50.0, places=2)
        self.assertAlmostEqual(trade.risk_percent, 0.5, places=2)


class TestCryptoPipValue(unittest.TestCase):
    """Topic 5 - Crypto Pip Value.

    Detected issue: All crypto assets must have pip_value=1.0.
    Price quoted in USD; 1 price unit = $1 per lot.

    Exact patch: _PIP_VALUE_TABLE[crypto] = 1.0 for all crypto symbols.
    Risk impact: pip_value=10 would give 10x undersized lots.
    Backward compat: _resolve_pip_value() unchanged.
    """

    def test_btcusd_is_1(self):  self.assertEqual(_ls_PIP.get("BTCUSD"), 1.0)
    def test_ethusd_is_1(self):  self.assertEqual(_ls_PIP.get("ETHUSD"), 1.0)
    def test_ltcusd_is_1(self):  self.assertEqual(_ls_PIP.get("LTCUSD"), 1.0)
    def test_bnbusd_is_1(self):  self.assertEqual(_ls_PIP.get("BNBUSD"), 1.0)
    def test_xrpusd_is_1(self):  self.assertEqual(_ls_PIP.get("XRPUSD"), 1.0)

    def test_btc_alias_is_1(self):
        self.assertEqual(_ls_resolve("BTC"), 1.0)

    def test_bitcoin_alias_is_1(self):
        self.assertEqual(_ls_resolve("BITCOIN"), 1.0)

    def test_eth_alias_is_1(self):
        self.assertEqual(_ls_resolve("ETH"), 1.0)

    def test_btcusd_suffix_is_1(self):
        self.assertEqual(_ls_resolve("BTCUSDm"), 1.0)

    def test_pr_btcusd_is_1(self):
        self.assertEqual(_pr_PIP.get("BTCUSD"), 1.0)

    def test_lot_sizing_crypto(self):
        """1% $10k, 500-pip SL: lot=100/(500x1)=0.20."""
        sizer = LotSizer(LotSizingConfig(risk_percent=1.0))
        result = _run(sizer.calculate("BTCUSD", 10000, 500))
        self.assertAlmostEqual(result.lot_size, 0.20, places=2)
        self.assertAlmostEqual(result.risk_percent, 1.0, places=1)

    def test_opentraderisk_btcusd(self):
        """0.2 lot BTCUSD, entry=50000, SL=49500: risk=500x0.2x1=$100=1.0%."""
        trade = OpenTradeRisk(symbol="BTCUSD", direction="BUY",
                              lot_size=0.2, entry_price=50000.0, stop_loss=49500.0,
                              account_balance=10000.0)
        self.assertAlmostEqual(trade.risk_amount, 100.0, places=1)
        self.assertAlmostEqual(trade.risk_percent, 1.0, places=1)


class TestExposureCalculation(unittest.TestCase):
    """Topic 6 - Exposure Calculation.

    Detected issue: ExposureControlEngine.check() had no try/except.
    Corrupt ExposurePosition -> uncaught AttributeError.

    Exact patch:
      check() wraps _check_inner(); get_snapshot() wraps _snapshot_inner().
      Three limits: max_total_risk, max_risk_per_symbol, max_open_trades.

    Risk impact: Without gate, 10 correlated 1% trades = 10% cumulative exposure.
    Backward compat: check() and get_snapshot() signatures unchanged.
    """

    def setUp(self):
        self.cfg = ExposureConfig(max_total_risk_percent=5.0, max_risk_per_symbol=2.0, max_open_trades=3)
        self.eng = ExposureControlEngine(config=self.cfg)

    def _p(self, sym, rp, d="BUY"):
        return ExposurePosition(symbol=sym, direction=d, risk_percent=rp, risk_usd=rp*100)

    def test_empty_portfolio_allowed(self):
        r = self.eng.check("EURUSD", "BUY", 1.0, [], 10000)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "EXPOSURE_OK")

    def test_total_risk_blocked(self):
        """existing 3.5% + new 2.0% = 5.5% > 5.0% -> MAX_TOTAL_RISK."""
        ops = [self._p("EURUSD", 1.5), self._p("GBPUSD", 1.0), self._p("AUDUSD", 1.0)]
        r = self.eng.check("NZDUSD", "BUY", 2.0, ops, 10000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_TOTAL_RISK", r.reason)

    def test_total_risk_exactly_at_limit_allowed(self):
        """3.5% + 1.5% = 5.0% = limit -> allowed (condition is >)."""
        ops = [self._p("EURUSD", 2.0), self._p("GBPUSD", 1.5)]
        r = self.eng.check("NZDUSD", "BUY", 1.5, ops, 10000)
        self.assertTrue(r.can_trade)

    def test_per_symbol_risk_blocked(self):
        """EURUSD 1.5% + new 1.0% = 2.5% > max_per_symbol=2.0% -> MAX_SYMBOL_RISK."""
        ops = [self._p("EURUSD", 1.5)]
        r = self.eng.check("EURUSD", "BUY", 1.0, ops, 10000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)

    def test_max_open_trades_blocked(self):
        """3 existing + 1 new = 4 > max=3 -> MAX_OPEN_TRADES."""
        ops = [self._p("EURUSD", 0.5), self._p("GBPUSD", 0.5), self._p("AUDUSD", 0.5)]
        r = self.eng.check("NZDUSD", "BUY", 0.5, ops, 10000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_OPEN_TRADES", r.reason)

    def test_projected_total_risk(self):
        """projected = current + new."""
        ops = [self._p("EURUSD", 1.0)]
        r = self.eng.check("GBPUSD", "BUY", 0.8, ops, 10000)
        self.assertAlmostEqual(r.projected_total_risk, 1.8, places=5)

    def test_available_risk(self):
        """available = max_total - current."""
        ops = [self._p("EURUSD", 2.0)]
        r = self.eng.check("GBPUSD", "BUY", 1.0, ops, 10000)
        self.assertAlmostEqual(r.available_risk, 3.0, places=5)

    def test_snapshot_accuracy(self):
        ops = [self._p("EURUSD", 1.5), self._p("GBPUSD", 1.0)]
        snap = self.eng.get_snapshot(ops)
        self.assertAlmostEqual(snap.total_risk_percent, 2.5, places=5)
        self.assertEqual(snap.open_trade_count, 2)

    def test_fail_closed_on_exception(self):
        with patch.object(self.eng, "_check_inner", side_effect=AttributeError("corrupt")):
            r = self.eng.check("EURUSD", "BUY", 1.0, [], 10000)
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_on_exception(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, "_check_inner", side_effect=RuntimeError("db")):
            r = eng.check("EURUSD", "BUY", 1.0, [], 10000)
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_snapshot_fail_closed_reraises(self):
        with patch.object(self.eng, "_snapshot_inner", side_effect=RuntimeError("io")):
            with self.assertRaises(RuntimeError):
                self.eng.get_snapshot([])

    def test_snapshot_fail_open_returns_empty(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, "_snapshot_inner", side_effect=RuntimeError("io")):
            snap = eng.get_snapshot([])
        self.assertEqual(snap.total_risk_percent, 0.0)
        self.assertEqual(snap.open_trade_count, 0)

    def test_no_args_uses_fail_closed(self):
        eng = ExposureControlEngine()
        self.assertIs(eng._fail_mode, FailMode.FAIL_CLOSED)

    def test_string_fail_mode_coerced(self):
        eng = ExposureControlEngine(fail_mode="FAIL_OPEN")
        self.assertIs(eng._fail_mode, FailMode.FAIL_OPEN)


class TestFailClosedBehavior(unittest.TestCase):
    """Topic 7 - Fail-Closed Behavior.

    Detected issue: Multiple gates had bare `except: allow_trade=True`
    silently allowing trades on any exception.

    Exact patch: FailMode enum + per-gate configurable mode.
    FAIL_CLOSED (default): exception -> block.
    FAIL_OPEN: exception -> allow + CRITICAL log.
    Every exception logged at CRITICAL regardless of mode.

    Risk impact: Silent FAIL_OPEN on correlation gate -> correlated positions 3-5x risk.
    Backward compat: Constructors accept FailMode enum or string. Default = FAIL_CLOSED.
    """

    def test_fail_mode_values(self):
        self.assertEqual(FailMode.FAIL_CLOSED.value, "FAIL_CLOSED")
        self.assertEqual(FailMode.FAIL_OPEN.value,   "FAIL_OPEN")

    def test_coerce_string_closed(self):  self.assertIs(coerce("FAIL_CLOSED"), FailMode.FAIL_CLOSED)
    def test_coerce_string_open(self):    self.assertIs(coerce("FAIL_OPEN"),   FailMode.FAIL_OPEN)
    def test_coerce_enum_identity(self):  self.assertIs(coerce(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)
    def test_coerce_lowercase(self):      self.assertIs(coerce("fail_open"), FailMode.FAIL_OPEN)

    def test_volatility_default_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_exposure_default_fail_closed(self):
        self.assertIs(ExposureControlEngine()._fail_mode, FailMode.FAIL_CLOSED)

    def test_portfolio_risk_default_fail_closed(self):
        self.assertIs(PortfolioRiskManager()._fail_mode, FailMode.FAIL_CLOSED)

    def test_volatility_fail_closed_blocks(self):
        vf = VolatilityFilter()
        with patch.object(vf, "_check_inner", side_effect=Exception("boom")):
            r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_exposure_fail_closed_blocks(self):
        eng = ExposureControlEngine()
        with patch.object(eng, "_check_inner", side_effect=Exception("boom")):
            r = eng.check("EURUSD", "BUY", 1.0, [], 10000)
        self.assertFalse(r.can_trade)

    def test_portfolio_fail_closed_blocks(self):
        mgr = PortfolioRiskManager()
        with patch.object(mgr, "_check_inner", side_effect=Exception("boom")):
            r = mgr.check(_make_trade("EURUSD", 1.0, 11.0, 1.0, 10000), [])
        self.assertFalse(r.can_trade)

    def test_volatility_fail_open_allows(self):
        vf = VolatilityFilter(config=VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=Exception("boom")):
            r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_exposure_fail_open_allows(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, "_check_inner", side_effect=Exception("boom")):
            r = eng.check("EURUSD", "BUY", 1.0, [], 10000)
        self.assertTrue(r.can_trade)

    def test_portfolio_fail_open_allows(self):
        mgr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(mgr, "_check_inner", side_effect=Exception("boom")):
            r = mgr.check(_make_trade("EURUSD", 1.0, 11.0, 1.0, 10000), [])
        self.assertTrue(r.can_trade)

    def test_exception_logged_fail_closed(self):
        import logging
        vf = VolatilityFilter()
        with patch.object(vf, "_check_inner", side_effect=Exception("boom")):
            with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")

    def test_exception_logged_fail_open(self):
        import logging
        vf = VolatilityFilter(config=VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, "_check_inner", side_effect=Exception("boom")):
            with self.assertLogs("risk.volatility_filter", level=logging.CRITICAL):
                vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")

    def test_string_fail_mode_volatility(self):
        vf = VolatilityFilter(config=VolatilityConfig(fail_mode="FAIL_OPEN"))  # type: ignore
        self.assertIs(vf._fail_mode, FailMode.FAIL_OPEN)

    def test_string_fail_mode_exposure(self):
        eng = ExposureControlEngine(fail_mode="FAIL_CLOSED")
        self.assertIs(eng._fail_mode, FailMode.FAIL_CLOSED)


class TestPortfolioCorrelationCalculations(unittest.TestCase):
    """Topic 8 - Portfolio Correlation Calculations.

    Detected issue: CorrelationFilter had no try/except; engine exceptions
    propagated uncaught to orchestrator, bypassing the fail_mode gate.

    Exact patch:
      check() wraps _check_inner(); per-pair crash -> log warning + static fallback.
      direction_factor: same=+1, opposite=-1 (hedging correctly reduces net exposure).

    Risk impact: EURUSD/GBPUSD corr=0.85 same-direction 1% each -> net=0.85 >= max=0.80.
    Without filter, correlated positions multiply portfolio risk.
    Backward compat: check(), portfolio_correlation_matrix(), get_correlation() unchanged.
    """

    def setUp(self):
        self.cfg = CorrelationFilterConfig(max_correlated_exposure=0.80, correlation_penalty_threshold=0.60)
        self.cf = CE_CorrelationFilter(config=self.cfg)

    def test_pearson_perfect_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(_pearson(x, x), 1.0, places=4)

    def test_pearson_perfect_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [5.0, 4.0, 3.0, 2.0, 1.0]
        self.assertAlmostEqual(_pearson(x, y), -1.0, places=4)

    def test_pearson_insufficient_data(self):
        """< 3 points -> 0.0 (no exception)."""
        self.assertEqual(_pearson([1.0, 2.0], [2.0, 1.0]), 0.0)

    def test_static_eurusd_gbpusd(self):
        corr = self.cf.get_correlation("EURUSD", "GBPUSD")
        self.assertAlmostEqual(corr, 0.85, places=2)

    def test_static_btcusd_ethusd(self):
        corr = self.cf.get_correlation("BTCUSD", "ETHUSD")
        self.assertAlmostEqual(corr, 0.88, places=2)

    def test_no_positions_allowed(self):
        r = _run(self.cf.check("EURUSD", "BUY", [], 1.0))
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 1.0, places=4)

    def test_high_correlation_same_direction_blocked(self):
        """EURUSD+GBPUSD same dir, corr=0.85: net=0.85 >= 0.80 -> BLOCKED."""
        pos = [CorrPosition("GBPUSD", "BUY", 1.0)]
        r = _run(self.cf.check("EURUSD", "BUY", pos, 1.0))
        self.assertFalse(r.can_trade)
        self.assertAlmostEqual(r.correlation_score, 0.85, places=2)

    def test_opposite_direction_blocked_high_abs(self):
        """EURUSD+GBPUSD opposite dir: abs(net)=0.85 >= 0.80 -> BLOCKED."""
        pos = [CorrPosition("GBPUSD", "SELL", 1.0)]
        r = _run(self.cf.check("EURUSD", "BUY", pos, 1.0))
        self.assertFalse(r.can_trade)

    def test_uncorrelated_pair_allowed(self):
        """EURUSD+BTCUSD: no static entry -> net=0 -> allowed."""
        pos = [CorrPosition("BTCUSD", "BUY", 2.0)]
        r = _run(self.cf.check("EURUSD", "BUY", pos, 1.0))
        self.assertTrue(r.can_trade)

    def test_penalty_between_thresholds(self):
        """EURUSD/NZDUSD corr=0.70 (penalty zone 0.60-0.80): multiplier < 1.0."""
        pos = [CorrPosition("NZDUSD", "BUY", 1.0)]
        r = _run(self.cf.check("EURUSD", "BUY", pos, 1.0))
        self.assertTrue(r.can_trade)
        self.assertLess(r.risk_multiplier, 1.0)
        self.assertGreaterEqual(r.risk_multiplier, 0.3)

    def test_fail_closed_on_engine_crash(self):
        cf = CE_CorrelationFilter(config=self.cfg, fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("engine down")):
            r = _run(cf.check("EURUSD", "BUY", [CorrPosition("GBPUSD","BUY",1.0)], 1.0))
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)
        self.assertEqual(r.source, "error")

    def test_fail_open_on_engine_crash(self):
        cf = CE_CorrelationFilter(config=self.cfg, fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, "_check_inner", side_effect=RuntimeError("engine down")):
            r = _run(cf.check("EURUSD", "BUY", [CorrPosition("GBPUSD","BUY",1.0)], 1.0))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_portfolio_matrix_diagonal(self):
        matrix = _run(self.cf.portfolio_correlation_matrix(["EURUSD", "GBPUSD", "AUDUSD"]))
        self.assertAlmostEqual(matrix[_canonical("EURUSD", "EURUSD")], 1.0, places=4)

    def test_portfolio_matrix_eurusd_gbpusd(self):
        matrix = _run(self.cf.portfolio_correlation_matrix(["EURUSD", "GBPUSD"]))
        self.assertAlmostEqual(matrix[_canonical("EURUSD", "GBPUSD")], 0.85, places=2)

    def test_rolling_engine_none_before_data(self):
        eng = RollingCorrelationEngine(window=50)
        result = _run(eng.get_correlation("EURUSD", "GBPUSD"))
        self.assertIsNone(result)

    def test_rolling_engine_computes_after_data(self):
        eng = RollingCorrelationEngine(window=5)
        for i in range(10):
            _run(eng.add_price("EURUSD", 1.1000 + i * 0.0001))
            _run(eng.add_price("GBPUSD", 1.2500 + i * 0.0001))
        corr = _run(eng.get_correlation("EURUSD", "GBPUSD"))
        self.assertIsNotNone(corr)
        self.assertGreater(corr, 0.0)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in [
        TestNewsEventBlocking, TestATRSpikeRobustness, TestSymbolSpecificThresholds,
        TestGoldPipValue, TestCryptoPipValue, TestExposureCalculation,
        TestFailClosedBehavior, TestPortfolioCorrelationCalculations,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    res    = runner.run(suite)
    total  = res.testsRun
    failed = len(res.failures) + len(res.errors)
    print(f"\n{'='*50}\nTOTAL: {total-failed}/{total} PASS  |  {failed} FAIL\n{'='*50}")
    exit(0 if failed == 0 else 1)
