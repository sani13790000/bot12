"""
FIX #8 -- TEST COVERAGE
=======================
Production-ready tests for 8 topics.
Each test class documents:
  1. Detected issue (what was broken)
  2. Exact patch applied (what changed in production code)
  3. Risk impact (what could go wrong without the fix)
  4. Backward compatibility (what remains unchanged)

All values are derived directly from production source code audit.
All tests were verified to pass against actual production files.

Run: python -m pytest test_fix8_coverage.py -v
"""
from __future__ import annotations

import asyncio
import logging
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/home/definable/fix8_definitive")

from fail_mode import FailMode, coerce

import lot_sizing as _ls_mod
from lot_sizing import (
    LotSizer,
    LotSizingConfig,
    LotSizeResult,
    _PIP_VALUE_TABLE as _LS_PIP,
    _SYMBOL_ALIASES as _LS_ALIASES,
)

import volatility_filter as _vf_mod
from volatility_filter import (
    VolatilityFilter,
    VolatilityFilterConfig,
    VolatilityCheckResult,
    VolatilityLevel,
    SymbolThresholds,
    _DEFAULT_SYMBOL_THRESHOLDS,
    FailMode as _VF_FailMode,
)

import portfolio_risk as _pr_mod
from portfolio_risk import (
    PortfolioRiskManager,
    PortfolioRiskConfig,
    PortfolioRiskResult,
    OpenTradeRisk,
    RiskLevel,
    TradeDirection,
    _PIP_VALUE_TABLE as _PR_PIP,
    _get_pip_value,
    _get_pip_value_with_source,
    FailMode as _PR_FailMode,
)

import exposure_control as _ec_mod
from exposure_control import (
    ExposureControlEngine,
    ExposureControlConfig,
    ExposureCheckResult,
    ExposurePosition,
    ExposureSnapshot,
    FailMode as _EC_FailMode,
)

import correlation_filter as _cf_mod
from correlation_filter import (
    CorrelationFilter,
    CorrelationFilterConfig,
    CorrelationResult,
    CorrPosition,
    FailMode as _CF_FailMode,
)


def _otr(symbol="EURUSD", direction="BUY", lot=1.0,
         entry=1.1100, sl=1.1000, balance=10_000.0):
    return OpenTradeRisk(
        symbol=symbol, direction=TradeDirection(direction),
        lot_size=lot, entry_price=entry, stop_loss=sl,
        account_balance=balance,
    )


def _ep(symbol="EURUSD", direction="BUY", risk_pct=1.0):
    return ExposurePosition(symbol=symbol, direction=direction, risk_percent=risk_pct)


def _cp(symbol="EURUSD", direction="BUY", risk_pct=1.0):
    return CorrPosition(symbol=symbol, direction=direction, risk_percent=risk_pct)


def _run(coro):
    return asyncio.run(coro)


class TestNewsEventBlocking(unittest.TestCase):
    """
    Issue: PortfolioRiskManager had no try/except before FIX #6.
           XAUUSD pip_value=10.0 (wrong) before FIX #4 -> Gold limits never fired.
    Patch: pip=1.0; check() wraps _check_inner() in try/except with FailMode.
    Risk:  5-lot NFP trade bypassed 2% single-trade limit.
    Compat: check(), check_async() signatures unchanged.
    Formula: risk_pct = abs(entry-sl) * lot * pip_value / balance * 100
             EURUSD pip=10: dist=0.01, lot=1000, bal=10000 -> 1.0%
    """

    def setUp(self):
        self.cfg = PortfolioRiskConfig(
            max_single_trade_risk_percent=2.0,
            max_portfolio_risk_percent=5.0,
        )
        self.mgr = PortfolioRiskManager(config=self.cfg)

    def test_otr_risk_formula_eurusd_1pct(self):
        t = _otr("EURUSD", "BUY", lot=1000.0, entry=1.1100, sl=1.1000, balance=10_000)
        self.assertAlmostEqual(t.risk_percent, 1.0, delta=0.001)
        self.assertAlmostEqual(t.risk_amount,  100.0, delta=0.01)
        self.assertAlmostEqual(t.pip_value_used, 10.0, places=4)

    def test_otr_risk_formula_eurusd_allowed_below_2pct(self):
        t = _otr("EURUSD", "BUY", lot=999.0, entry=1.1200, sl=1.1000, balance=10_000)
        self.assertLess(t.risk_percent, 2.0)
        r = self.mgr.check(t, [])
        self.assertTrue(r.can_trade)

    def test_single_trade_blocked_above_limit(self):
        t = _otr("EURUSD", "BUY", lot=1001.0, entry=1.1200, sl=1.1000, balance=10_000)
        self.assertGreater(t.risk_percent, 2.0)
        r = self.mgr.check(t, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK_TOO_HIGH", r.reason)

    def test_portfolio_blocked_when_total_exceeds(self):
        symbols = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCHF"]
        existing = [_otr(sym, "BUY", lot=1000.0, entry=1.11, sl=1.10, balance=10_000)
                    for sym in symbols]
        new_t = _otr("EURGBP", "BUY", lot=1000.0, entry=0.86, sl=0.85, balance=10_000)
        projected = sum(t.risk_percent for t in existing) + new_t.risk_percent
        self.assertGreater(projected, 5.0)
        r = self.mgr.check(new_t, existing)
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_RISK_TOO_HIGH", r.reason)

    def test_portfolio_allowed_when_total_below_limit(self):
        symbols = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
        existing = [_otr(sym, "BUY", lot=1000.0, entry=1.11, sl=1.10, balance=10_000)
                    for sym in symbols]
        new_t = _otr("EURJPY", "BUY", lot=1000.0, entry=1.31, sl=1.30, balance=10_000)
        r = self.mgr.check(new_t, existing)
        self.assertTrue(r.can_trade)

    def test_check_async_mirrors_sync(self):
        t = _otr("EURUSD", "BUY", lot=999.0, entry=1.12, sl=1.10, balance=10_000)
        sync_r  = self.mgr.check(t, [])
        async_r = _run(self.mgr.check_async(t, []))
        self.assertEqual(sync_r.can_trade, async_r.can_trade)
        self.assertEqual(sync_r.reason,    async_r.reason)

    def test_fail_closed_exception_blocks(self):
        cfg = PortfolioRiskConfig(fail_mode=_PR_FailMode.FAIL_CLOSED)
        mgr = PortfolioRiskManager(config=cfg)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.portfolio", level=logging.ERROR):
                r = mgr.check(_otr(), [])
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_exception_allows(self):
        cfg = PortfolioRiskConfig(fail_mode=_PR_FailMode.FAIL_OPEN)
        mgr = PortfolioRiskManager(config=cfg)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.portfolio", level=logging.ERROR):
                r = mgr.check(_otr(), [])
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_gold_trade_correct_pip_value(self):
        t = _otr("XAUUSD", "BUY", lot=10.0, entry=2100.0, sl=2000.0, balance=10_000)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 10.0, delta=0.01)


class TestATRSpikeRobustness(unittest.TestCase):
    """
    Issue: VolatilityFilter.check() no try/except before FIX #6.
           avg_atr=0 -> ZeroDivisionError -> uncaught -> trade allowed.
    Patch: check() wraps _check_inner() in try/except with FailMode.
    Thresholds (defaults): extreme>=3.5 -> BLOCKED; high>=2.0 -> HIGH;
                           spread>3.0 -> BLOCKED. All strictly comparative.
    Risk: 4x ATR spike = actual SL 4x bigger -> 4% risk vs 1% intended.
    """

    def setUp(self):
        self.cfg  = VolatilityFilterConfig(atr_history_bars=10)
        self.vf   = VolatilityFilter(config=self.cfg)
        self.hist = [0.001] * 10

    def test_normal_atr_allowed(self):
        r = self.vf.check(0.001, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.NORMAL)
        self.assertAlmostEqual(r.lot_multiplier, 1.0, places=4)

    def test_extreme_atr_blocked(self):
        r = self.vf.check(0.0035, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.EXTREME)
        self.assertIn("EXTREME_VOLATILITY", r.reason)

    def test_extreme_boundary_at_threshold(self):
        r = self.vf.check(0.0035, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_just_below_extreme_is_high(self):
        r = self.vf.check(0.003499, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.HIGH)

    def test_high_volatility_above_threshold_reduces_lot(self):
        """ratio=2.5: lot_mult = max(0.1, 1-(2.5-2.0)/(3.5-2.0)) = 0.667"""
        r = self.vf.check(0.0025, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.HIGH)
        self.assertAlmostEqual(r.lot_multiplier, 0.667, delta=0.01)
        self.assertLess(r.lot_multiplier, 1.0)

    def test_spread_too_high_blocked(self):
        r = self.vf.check(0.001, self.hist, 0.0004, 0.0001, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_HIGH", r.reason)

    def test_spread_at_max_allowed(self):
        r = self.vf.check(0.001, self.hist, 0.0003, 0.0001, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_zero_avg_atr_safe_default(self):
        r = self.vf.check(0.001, [0.0]*10, 0.0002, 0.0002, "EURUSD")
        self.assertIsInstance(r, VolatilityCheckResult)
        self.assertTrue(r.can_trade)

    def test_fail_closed_via_config_exception_blocks(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=_VF_FailMode.FAIL_CLOSED))
        with patch.object(vf, '_check_inner', side_effect=ZeroDivisionError("forced")):
            with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                r = vf.check(0.001, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_via_config_exception_allows(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=_VF_FailMode.FAIL_OPEN))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                r = vf.check(0.001, self.hist, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_exception_always_logged_regardless_of_mode(self):
        for fm in (_VF_FailMode.FAIL_CLOSED, _VF_FailMode.FAIL_OPEN):
            with self.subTest(fail_mode=fm):
                vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=fm))
                with patch.object(vf, '_check_inner', side_effect=RuntimeError("test")):
                    with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                        vf.check(0.001, self.hist, 0.0002, 0.0002, "EURUSD")


class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    Issue: One global threshold for all assets. BTC normal 8x avg -> always blocked.
    Patch: _DEFAULT_SYMBOL_THRESHOLDS dict with per-asset extreme values.
           XAUUSD: extreme=3.0 (tighter); BTCUSD: extreme=2.2 (lower).
    Risk: Wrong threshold -> Gold blocked in $1 ATR / BTC allowed in 6x crash.
    """

    def setUp(self):
        self.hist = [1.0] * 20

    def test_default_thresholds_table_exists(self):
        for sym in ("EURUSD", "XAUUSD", "BTCUSD", "GBPUSD"):
            self.assertIn(sym, _DEFAULT_SYMBOL_THRESHOLDS)

    def test_gold_tighter_extreme_threshold(self):
        vf = VolatilityFilter()
        r  = vf.check(3.1, self.hist, 0.5, 0.5, "XAUUSD")
        self.assertFalse(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.EXTREME)

    def test_gold_below_extreme_high(self):
        vf = VolatilityFilter()
        r  = vf.check(2.9, self.hist, 0.5, 0.5, "XAUUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.HIGH)

    def test_btc_lower_extreme_threshold(self):
        vf = VolatilityFilter()
        r  = vf.check(2.3, self.hist, 0.5, 0.5, "BTCUSD")
        self.assertFalse(r.can_trade)
        self.assertEqual(r.level, VolatilityLevel.EXTREME)

    def test_custom_threshold_override(self):
        vf = VolatilityFilter()
        vf.add_symbol_threshold("BTCUSD", SymbolThresholds(0.5, 3.0, 10.0))
        r = vf.check(9.0, self.hist, 0.5, 0.5, "BTCUSD")
        self.assertTrue(r.can_trade)

    def test_unknown_symbol_uses_config_extreme(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(
            extreme_volatility_ratio=3.5, high_volatility_ratio=2.0
        ))
        r1 = vf.check(3.4, self.hist, 0.5, 0.5, "EXOTIC123")
        self.assertTrue(r1.can_trade)
        r2 = vf.check(3.6, self.hist, 0.5, 0.5, "EXOTIC123")
        self.assertFalse(r2.can_trade)

    def test_cache_isolation_between_symbols(self):
        vf = VolatilityFilter()
        r1 = vf.check(3.6, self.hist, 0.5, 0.5, "EURUSD")
        r2 = vf.check(1.0, self.hist, 0.5, 0.5, "GBPUSD")
        self.assertFalse(r1.can_trade)
        self.assertTrue(r2.can_trade)

    def test_symbol_threshold_validation_low_ge_high(self):
        with self.assertRaises(ValueError):
            SymbolThresholds(low=3.5, high=2.0, extreme=1.0)

    def test_symbol_threshold_validation_negative(self):
        with self.assertRaises(ValueError):
            SymbolThresholds(low=-0.1, high=2.0, extreme=3.5)


class TestGoldPipValue(unittest.TestCase):
    """
    Issue (FIX #4): XAUUSD pip=10.0 in both modules (10x wrong).
                    Correct: $0.01/oz * 100oz lot = $1.00.
    Patch: lot_sizing 'XAUUSD':1.0; portfolio_risk "XAUUSD":1.0.
    Risk: pip=10 -> lot 10x undersized -> actual risk 10% of intended.
    """

    def test_ls_xauusd_equals_1(self):
        self.assertEqual(_LS_PIP["XAUUSD"], 1.0)

    def test_pr_xauusd_equals_1(self):
        self.assertEqual(_PR_PIP["XAUUSD"], 1.0)

    def test_pr_xagusd_equals_50(self):
        self.assertEqual(_PR_PIP["XAGUSD"], 50.0)

    def test_ls_xagusd_equals_50(self):
        self.assertEqual(_LS_PIP["XAGUSD"], 50.0)

    def test_gold_alias_resolves_to_1(self):
        self.assertEqual(_get_pip_value("GOLD"), 1.0)

    def test_silver_alias_resolves_to_50(self):
        self.assertEqual(_get_pip_value("SILVER"), 50.0)

    def test_xauusd_broker_suffix_strip(self):
        self.assertEqual(_get_pip_value("XAUUSDm"), 1.0)

    def test_get_pip_value_with_source(self):
        val, src = _get_pip_value_with_source("XAUUSD")
        self.assertEqual(val, 1.0)
        self.assertIn(src, ("table", "alias", "suffix", "injected"))

    def test_gold_otr_risk_not_10x_inflated(self):
        t = _otr("XAUUSD", "BUY", lot=10.0, entry=2005.0, sl=2000.0, balance=10_000)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertLess(t.risk_amount, 200.0)

    def test_gold_otr_risk_percent_correct(self):
        t = _otr("XAUUSD", "BUY", lot=1.0, entry=2100.0, sl=2000.0, balance=10_000)
        self.assertAlmostEqual(t.risk_percent, 1.0, delta=0.01)

    def test_lot_sizer_gold_pip_value(self):
        async def _get():
            val, src = await LotSizer().get_pip_value("XAUUSD")
            return val
        val = _run(_get())
        self.assertEqual(val, 1.0)

    def test_lot_sizer_gold_not_0_2(self):
        sizer = LotSizer(config=LotSizingConfig(risk_percent=1.0))
        async def _calc():
            return await sizer.calculate(10_000.0, 50.0, "XAUUSD")
        r = _run(_calc())
        self.assertAlmostEqual(r.pip_value_used, 1.0, places=4)
        self.assertGreater(r.lot_size, 0.5)


class TestCryptoPipValue(unittest.TestCase):
    """
    Issue (FIX #4): ETHUSD pip=0.01 -> lot 100x too large -> account blown.
    Patch: all crypto = 1.0 in both modules.
    """

    CRYPTO_SYMS = ["BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"]

    def test_ls_crypto_pip_values_all_1(self):
        for sym in self.CRYPTO_SYMS:
            with self.subTest(sym=sym):
                self.assertEqual(_LS_PIP[sym], 1.0)

    def test_pr_crypto_pip_values_all_1(self):
        for sym in self.CRYPTO_SYMS:
            with self.subTest(sym=sym):
                self.assertEqual(_PR_PIP[sym], 1.0)

    def test_btc_alias_resolves(self):
        self.assertEqual(_get_pip_value("BTC"), 1.0)

    def test_eth_alias_resolves(self):
        self.assertEqual(_get_pip_value("ETH"), 1.0)

    def test_btcusd_broker_suffix_strip(self):
        self.assertEqual(_get_pip_value("BTCUSDm"), 1.0)

    def test_ethusd_broker_suffix_strip(self):
        self.assertEqual(_get_pip_value("ETHUSDm"), 1.0)

    def test_ls_btc_get_pip_value(self):
        async def _get():
            return await LotSizer().get_pip_value("BTC")
        val, _ = _run(_get())
        self.assertEqual(val, 1.0)

    def test_btc_otr_risk_correct(self):
        t = _otr("BTCUSD", "BUY", lot=0.1, entry=50_500.0, sl=50_000.0, balance=10_000)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 0.5, delta=0.01)

    def test_eth_otr_risk_correct(self):
        t = _otr("ETHUSD", "BUY", lot=0.1, entry=3_100.0, sl=3_000.0, balance=10_000)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 0.1, delta=0.01)

    def test_btc_lot_sizer_reasonable(self):
        sizer = LotSizer(config=LotSizingConfig(risk_percent=1.0))
        async def _calc():
            return await sizer.calculate(10_000.0, 500.0, "BTCUSD")
        r = _run(_calc())
        self.assertAlmostEqual(r.pip_value_used, 1.0, places=4)
        self.assertGreater(r.lot_size, 0.05)
        self.assertLess(r.lot_size, 2.0)

    def test_xrpusd_pip_value(self):
        self.assertEqual(_get_pip_value("XRPUSD"), 1.0)

    def test_ltcusd_pip_value(self):
        self.assertEqual(_get_pip_value("LTCUSD"), 1.0)


class TestExposureCalculation(unittest.TestCase):
    """
    Issue: check() no try/except before FIX #6. Hardcoded new_risk_pct=1.0 before FIX #5.
    Patch: try/except; new_risk_percent propagated from actual trade.
    Limits: max_total=5.0, max_symbol=2.0, max_currency=3.0, max_trades=5,
            max_buy=3, max_sell=3. All STRICTLY >.
    """

    def setUp(self):
        self.cfg = ExposureControlConfig()
        self.eng = ExposureControlEngine(config=self.cfg)

    def test_allowed_when_empty(self):
        r = self.eng.check("EURUSD", "BUY", 1.0, [])
        self.assertTrue(r.can_trade)

    def test_projected_total_risk_field(self):
        positions = [_ep("EURUSD", "BUY", risk_pct=2.0)]
        r = self.eng.check("GBPUSD", "BUY", 1.5, positions)
        self.assertAlmostEqual(r.projected_total_risk, 3.5, places=4)

    def test_total_exposure_blocked(self):
        positions = [_ep("EURUSD", "BUY",  1.0), _ep("GBPUSD", "SELL", 1.0),
                     _ep("AUDUSD", "BUY",  1.0), _ep("NZDUSD", "SELL", 1.0)]
        r = self.eng.check("USDCAD", "BUY", 1.5, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("Total exposure", r.reason)

    def test_total_exposure_boundary_allowed(self):
        """Use cross-pairs (no USD) so currency limit (3%) is not triggered.
        EURGBP+EURJPY+GBPJPY+EURCHF each 1% -> EUR=3%(limit), total=4%.
        new GBPCHF 1% -> GBP=3%(limit), CHF=2%, total=5.0%(limit) -> allowed.
        """
        positions = [
            _ep("EURGBP", "BUY",  1.0), _ep("EURJPY", "SELL", 1.0),
            _ep("GBPJPY", "BUY",  1.0), _ep("EURCHF", "SELL", 1.0),
        ]
        r = self.eng.check("GBPCHF", "BUY", 1.0, positions)
        self.assertTrue(r.can_trade)

    def test_symbol_exposure_blocked(self):
        positions = [_ep("EURUSD", "SELL", risk_pct=1.5)]
        r = self.eng.check("EURUSD", "BUY", 1.0, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("EURUSD", r.reason)

    def test_symbol_exposure_boundary_allowed(self):
        positions = [_ep("EURUSD", "SELL", risk_pct=1.0)]
        r = self.eng.check("EURUSD", "BUY", 1.0, positions)
        self.assertTrue(r.can_trade)

    def test_max_simultaneous_trades_blocked(self):
        positions = [_ep("EURUSD", "BUY",0.5), _ep("GBPUSD","BUY",0.5),
                     _ep("AUDUSD","SELL",0.5), _ep("NZDUSD","SELL",0.5),
                     _ep("USDCAD","BUY",0.5)]
        r = self.eng.check("USDJPY", "SELL", 0.5, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("simultaneous", r.reason)

    def test_max_trades_boundary_allowed(self):
        """2B+2S existing + 1B new = total=5=limit, buy=3=limit -> allowed"""
        positions = [_ep("EURGBP","BUY",0.5), _ep("EURJPY","BUY",0.5),
                     _ep("GBPJPY","SELL",0.5), _ep("EURCHF","SELL",0.5)]
        r = self.eng.check("GBPCHF", "BUY", 0.5, positions)
        self.assertTrue(r.can_trade)

    def test_duplicate_symbol_direction_blocked(self):
        positions = [_ep("EURUSD", "BUY", risk_pct=1.0)]
        r = self.eng.check("EURUSD", "BUY", 0.5, positions)
        self.assertFalse(r.can_trade)
        self.assertIn("Duplicate", r.reason)

    def test_fail_closed_exception_blocks(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=_EC_FailMode.FAIL_CLOSED)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                r = eng.check("EURUSD", "BUY", 1.0, [])
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_exception_allows(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=_EC_FailMode.FAIL_OPEN)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                r = eng.check("EURUSD", "BUY", 1.0, [])
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_get_snapshot_correct_totals(self):
        positions = [_ep("EURUSD","BUY",1.5), _ep("GBPUSD","SELL",1.0)]
        snap = self.eng.get_snapshot(positions)
        self.assertAlmostEqual(snap.total_risk_percent, 2.5, places=4)
        self.assertEqual(snap.open_trades, 2)

    def test_get_snapshot_fail_closed_returns_blocked(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=_EC_FailMode.FAIL_CLOSED)
        with patch.object(eng, '_snapshot_inner', side_effect=RuntimeError("snap")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                snap = eng.get_snapshot([])
        self.assertFalse(snap.can_open_new)

    def test_get_snapshot_fail_open_returns_open(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=_EC_FailMode.FAIL_OPEN)
        with patch.object(eng, '_snapshot_inner', side_effect=RuntimeError("snap")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                snap = eng.get_snapshot([])
        self.assertIsInstance(snap, ExposureSnapshot)
        self.assertTrue(snap.can_open_new)


class TestFailClosedBehaviour(unittest.TestCase):
    """
    Issue: CorrelationFilter had except: allow_trade=True (SILENT). Others: no try/except.
    Patch: fail_mode.py SSoT; all 4 gates default FAIL_CLOSED; every exception logged.
    Note on SSoT: running outside backend.risk package path each module falls back to
    its own FailMode via ImportError. Values are identical; class identity may differ.
    Tests verify value equality and behavioral correctness.
    """

    def test_fail_mode_string_values(self):
        self.assertEqual(FailMode.FAIL_CLOSED, "FAIL_CLOSED")
        self.assertEqual(FailMode.FAIL_OPEN,   "FAIL_OPEN")

    def test_fail_mode_is_str_subclass(self):
        self.assertIsInstance(FailMode.FAIL_CLOSED, str)

    def test_coerce_uppercase_strings(self):
        self.assertIs(coerce("FAIL_CLOSED"), FailMode.FAIL_CLOSED)
        self.assertIs(coerce("FAIL_OPEN"),   FailMode.FAIL_OPEN)

    def test_coerce_lowercase_strings(self):
        self.assertIs(coerce("fail_closed"), FailMode.FAIL_CLOSED)
        self.assertIs(coerce("fail_open"),   FailMode.FAIL_OPEN)

    def test_coerce_identity(self):
        self.assertIs(coerce(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)

    def test_coerce_invalid_raises(self):
        with self.assertRaises(ValueError):
            coerce("INVALID_MODE")

    def test_all_module_fail_modes_equal_fail_closed(self):
        for fm_cls in (_VF_FailMode, _PR_FailMode, _EC_FailMode, _CF_FailMode):
            with self.subTest(cls=fm_cls):
                self.assertEqual(fm_cls.FAIL_CLOSED, "FAIL_CLOSED")
                self.assertEqual(fm_cls.FAIL_OPEN,   "FAIL_OPEN")

    def test_volatility_filter_default_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode, _VF_FailMode.FAIL_CLOSED)

    def test_exposure_control_default_fail_closed(self):
        self.assertIs(ExposureControlEngine()._fail_mode, _EC_FailMode.FAIL_CLOSED)

    def test_correlation_filter_default_fail_closed(self):
        self.assertIs(CorrelationFilter()._fail_mode, _CF_FailMode.FAIL_CLOSED)

    def test_portfolio_risk_default_fail_closed(self):
        self.assertIs(PortfolioRiskManager()._fail_mode, _PR_FailMode.FAIL_CLOSED)

    def test_volatility_fail_open_via_config(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=_VF_FailMode.FAIL_OPEN))
        self.assertIs(vf._fail_mode, _VF_FailMode.FAIL_OPEN)

    def test_exposure_fail_open_via_kwarg(self):
        eng = ExposureControlEngine(fail_mode=_EC_FailMode.FAIL_OPEN)
        self.assertIs(eng._fail_mode, _EC_FailMode.FAIL_OPEN)

    def test_correlation_fail_open_via_kwarg(self):
        cf = CorrelationFilter(fail_mode=_CF_FailMode.FAIL_OPEN)
        self.assertIs(cf._fail_mode, _CF_FailMode.FAIL_OPEN)

    def test_portfolio_fail_open_via_config(self):
        cfg = PortfolioRiskConfig(fail_mode=_PR_FailMode.FAIL_OPEN)
        mgr = PortfolioRiskManager(config=cfg)
        self.assertIs(mgr._fail_mode, _PR_FailMode.FAIL_OPEN)

    def test_volatility_exception_logged(self):
        vf = VolatilityFilter(config=VolatilityFilterConfig(fail_mode=_VF_FailMode.FAIL_CLOSED))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                vf.check(1.0, [1.0]*5, 0.1, 0.1, "EURUSD")

    def test_exposure_exception_logged(self):
        eng = ExposureControlEngine(fail_mode=_EC_FailMode.FAIL_CLOSED)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                eng.check("EURUSD", "BUY", 1.0, [])

    def test_portfolio_exception_logged(self):
        cfg = PortfolioRiskConfig(fail_mode=_PR_FailMode.FAIL_CLOSED)
        mgr = PortfolioRiskManager(config=cfg)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.portfolio", level=logging.ERROR):
                mgr.check(_otr(), [])

    def test_correlation_exception_logged(self):
        cf = CorrelationFilter(fail_mode=_CF_FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("x")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                _run(cf.check("EURUSD", "BUY", [], 1.0))

    def test_fail_closed_blocks_on_exception(self):
        for cls, fm_cls, log_name, call in [
            (lambda: VolatilityFilter(config=VolatilityFilterConfig(fail_mode=_VF_FailMode.FAIL_CLOSED)),
             "_check_inner", "risk.volatility_filter",
             lambda obj: obj.check(1.0, [1.0]*5, 0.1, 0.1, "EURUSD")),
            (lambda: ExposureControlEngine(fail_mode=_EC_FailMode.FAIL_CLOSED),
             "_check_inner", "risk.exposure",
             lambda obj: obj.check("EURUSD", "BUY", 1.0, [])),
            (lambda: PortfolioRiskManager(config=PortfolioRiskConfig(fail_mode=_PR_FailMode.FAIL_CLOSED)),
             "_check_inner", "risk.portfolio",
             lambda obj: obj.check(_otr(), [])),
        ]:
            with self.subTest(log=log_name):
                obj = cls()
                with patch.object(obj, fm_cls, side_effect=RuntimeError("e")):
                    with self.assertLogs(log_name, level=logging.ERROR):
                        r = call(obj)
                self.assertFalse(r.can_trade)

    def test_fail_open_allows_on_exception(self):
        for cls, fm_cls, log_name, call in [
            (lambda: VolatilityFilter(config=VolatilityFilterConfig(fail_mode=_VF_FailMode.FAIL_OPEN)),
             "_check_inner", "risk.volatility_filter",
             lambda obj: obj.check(1.0, [1.0]*5, 0.1, 0.1, "EURUSD")),
            (lambda: ExposureControlEngine(fail_mode=_EC_FailMode.FAIL_OPEN),
             "_check_inner", "risk.exposure",
             lambda obj: obj.check("EURUSD", "BUY", 1.0, [])),
            (lambda: PortfolioRiskManager(config=PortfolioRiskConfig(fail_mode=_PR_FailMode.FAIL_OPEN)),
             "_check_inner", "risk.portfolio",
             lambda obj: obj.check(_otr(), [])),
        ]:
            with self.subTest(log=log_name):
                obj = cls()
                with patch.object(obj, fm_cls, side_effect=RuntimeError("e")):
                    with self.assertLogs(log_name, level=logging.ERROR):
                        r = call(obj)
                self.assertTrue(r.can_trade)


class TestPortfolioCorrelationCalcs(unittest.TestCase):
    """
    Issue: CorrelationFilter no outer try/except before FIX #6.
    Patch: check() outer try/except; FAIL_CLOSED blocks, FAIL_OPEN allows.
    Net exposure: sum(corr * dir_factor * pos.risk_pct)
    Block: abs(net) >= max_corr_exposure (0.80)
    Penalty: abs(net) >= penalty_threshold (0.60) -> reduce multiplier.
    """

    def setUp(self):
        self.cfg = CorrelationFilterConfig(
            max_correlated_exposure=0.80,
            correlation_penalty_threshold=0.60,
        )
        self.cf = CorrelationFilter(config=self.cfg)

    def test_static_table_eurusd_gbpusd(self):
        val = self.cf.get_correlation("EURUSD", "GBPUSD")
        self.assertIsNotNone(val)
        self.assertAlmostEqual(val, 0.85, places=2)

    def test_static_table_negative_corr(self):
        val = self.cf.get_correlation("EURUSD", "USDCHF")
        self.assertIsNotNone(val)
        self.assertLess(val, 0.0)

    def test_static_table_unknown_pair_none(self):
        self.assertIsNone(self.cf.get_correlation("EXOTIC1", "EXOTIC2"))

    def test_high_positive_corr_same_direction_blocked(self):
        positions = [_cp("GBPUSD", "BUY", risk_pct=1.0)]
        r = _run(self.cf.check("EURUSD", "BUY", positions, 1.0))
        self.assertFalse(r.can_trade)
        self.assertAlmostEqual(r.correlation_score, 0.85, delta=0.01)

    def test_high_positive_corr_opposite_direction_also_blocked(self):
        positions = [_cp("GBPUSD", "SELL", risk_pct=1.0)]
        r = _run(self.cf.check("EURUSD", "BUY", positions, 1.0))
        self.assertFalse(r.can_trade)

    def test_btc_eth_high_corr_blocked(self):
        positions = [_cp("ETHUSD", "BUY", risk_pct=1.0)]
        r = _run(self.cf.check("BTCUSD", "BUY", positions, 1.0))
        self.assertFalse(r.can_trade)

    def test_penalty_zone_reduces_multiplier(self):
        """GBPUSD/NZDUSD corr=0.68: penalty=1-(0.68-0.60)/(0.80-0.60)=0.6; mult=0.60"""
        positions = [_cp("NZDUSD", "BUY", risk_pct=1.0)]
        r = _run(self.cf.check("GBPUSD", "BUY", positions, 1.0))
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 0.60, delta=0.01)

    def test_empty_positions_always_allowed(self):
        r = _run(self.cf.check("EURUSD", "BUY", [], 1.0))
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 1.0, places=4)

    def test_unknown_pair_skipped_allowed(self):
        positions = [_cp("EXOTIC1", "BUY", risk_pct=1.0)]
        r = _run(self.cf.check("EXOTIC2", "BUY", positions, 1.0))
        self.assertTrue(r.can_trade)

    def test_block_threshold_boundary(self):
        """abs(net)=0.80 >= 0.80 -> blocked. Patch _get_correlation (internal)."""
        with patch.object(self.cf, '_get_correlation', return_value=(0.80, 'mock')):
            r = _run(self.cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",1.0)], 1.0))
        self.assertFalse(r.can_trade)

    def test_just_below_block_penalty_zone(self):
        """abs(net)=0.79 -> penalty zone. mult=max(0.3, 1-0.19/0.20)=0.30"""
        with patch.object(self.cf, '_get_correlation', return_value=(0.79, 'mock')):
            r = _run(self.cf.check("EURUSD", "BUY", [_cp("GBPUSD","BUY",1.0)], 1.0))
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 0.30, delta=0.01)

    def test_fail_closed_exception_blocks(self):
        cf = CorrelationFilter(config=self.cfg, fail_mode=_CF_FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                r = _run(cf.check("EURUSD", "BUY", [], 1.0))
        self.assertFalse(r.can_trade)
        self.assertEqual(r.source, "error")
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_exception_allows(self):
        cf = CorrelationFilter(config=self.cfg, fail_mode=_CF_FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("forced")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                r = _run(cf.check("EURUSD", "BUY", [], 1.0))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_default_fail_mode_is_fail_closed(self):
        self.assertIs(CorrelationFilter()._fail_mode, _CF_FailMode.FAIL_CLOSED)

    def test_correlation_result_fields_present(self):
        r = _run(self.cf.check("EURUSD", "BUY", [], 1.0))
        for fld in ("can_trade", "risk_multiplier", "correlation_score", "reason", "source"):
            self.assertTrue(hasattr(r, fld))

    def test_multiple_positions_net_accumulates(self):
        """2 positions * 0.45 = net=0.90 >= 0.80 -> blocked. Patch _get_correlation."""
        with patch.object(self.cf, '_get_correlation', return_value=(0.45, 'mock')):
            positions = [_cp("SYM1","BUY",1.0), _cp("SYM2","BUY",1.0)]
            r = _run(self.cf.check("EURUSD", "BUY", positions, 1.0))
        self.assertFalse(r.can_trade)
        self.assertAlmostEqual(r.correlation_score, 0.90, delta=0.01)


class TestIntegration(unittest.TestCase):
    """Regression guards: FIX #4 + FIX #5 + FIX #6 interactions."""

    def test_fix4_gold_pip_not_10(self):
        self.assertEqual(_LS_PIP["XAUUSD"], 1.0)
        self.assertEqual(_PR_PIP["XAUUSD"], 1.0)

    def test_fix4_gold_risk_not_10x(self):
        t = _otr("XAUUSD", "BUY", lot=1.0, entry=2100.0, sl=2000.0, balance=10_000)
        self.assertLess(t.risk_amount, 200.0)

    def test_fix5_real_risk_propagated_to_exposure(self):
        eng = ExposureControlEngine()
        r = eng.check("EURUSD", "BUY", 3.0, [])
        self.assertFalse(r.can_trade)

    def test_fix6_all_gates_default_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode,     _VF_FailMode.FAIL_CLOSED)
        self.assertIs(ExposureControlEngine()._fail_mode, _EC_FailMode.FAIL_CLOSED)
        self.assertIs(CorrelationFilter()._fail_mode,     _CF_FailMode.FAIL_CLOSED)
        self.assertIs(PortfolioRiskManager()._fail_mode,  _PR_FailMode.FAIL_CLOSED)

    def test_fix4_btc_pip_correct(self):
        async def _calc():
            return await LotSizer().calculate(10_000.0, 500.0, "BTCUSD")
        r = _run(_calc())
        self.assertGreater(r.lot_size, 0.05)
        self.assertLess(r.lot_size, 5.0)
        self.assertEqual(r.pip_value_used, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
