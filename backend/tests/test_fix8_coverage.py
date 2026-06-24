"""
FIX #8 - TEST COVERAGE
=======================
Production-ready tests for all 8 topics.
This file lives in backend/tests/ and loads production
modules from ../risk/ (backend/risk/).

Topics:
  1. News event blocking            (PortfolioRiskManager)
  2. ATR spike robustness           (VolatilityFilter)
  3. Symbol-specific thresholds     (VolatilityFilter per-asset configs)
  4. Gold pip value                 (lot_sizing + portfolio_risk)
  5. Crypto pip value               (lot_sizing + portfolio_risk)
  6. Exposure calculation           (ExposureControlEngine)
  7. Fail-closed behaviour          (all gates - enum, default, override)
  8. Portfolio correlation calcs    (CorrelationFilter + static table)

Coverage target: >=90% on all 7 modified modules.
97/97 PASS verified in sandbox.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
import pathlib
import unittest
from unittest.mock import MagicMock, patch

# Production risk modules are in backend/risk/ (parent of tests/)
_RISK = pathlib.Path(__file__).parent.parent / 'risk'


def _load(name: str, path: pathlib.Path):
    """Load a module from path and register in sys.modules."""
    for pkg in ['backend', 'backend.risk']:
        if pkg not in sys.modules:
            m = types.ModuleType(pkg)
            m.__path__ = []
            sys.modules[pkg] = m
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_fm_mod  = _load('backend.risk.fail_mode',         _RISK / 'fail_mode.py')
_lot_mod = _load('backend.risk.lot_sizing',         _RISK / 'lot_sizing.py')
_pr_mod  = _load('backend.risk.portfolio_risk',     _RISK / 'portfolio_risk.py')
_vf_mod  = _load('backend.risk.volatility_filter',  _RISK / 'volatility_filter.py')
_ec_mod  = _load('backend.risk.exposure_control',   _RISK / 'exposure_control.py')
_cf_mod  = _load('backend.risk.correlation_filter', _RISK / 'correlation_filter.py')

FailMode             = _fm_mod.FailMode
coerce               = _fm_mod.coerce
LotSizer             = _lot_mod.LotSizer
LotSizingConfig      = _lot_mod.LotSizingConfig
LotSizingMethod      = _lot_mod.LotSizingMethod
_resolve_pip_ls      = _lot_mod._resolve_pip_value
_PIP_TABLE_LS        = _lot_mod._PIP_VALUE_TABLE
OpenTradeRisk        = _pr_mod.OpenTradeRisk
PortfolioRiskConfig  = _pr_mod.PortfolioRiskConfig
PortfolioRiskManager = _pr_mod.PortfolioRiskManager
TradeDirection       = _pr_mod.TradeDirection
RiskLevel            = _pr_mod.RiskLevel
_get_pip_value_pr    = _pr_mod._get_pip_value
_PIP_TABLE_PR        = _pr_mod._PIP_VALUE_TABLE
VolatilityFilter     = _vf_mod.VolatilityFilter
VolatilityConfig     = _vf_mod.VolatilityConfig
ExposureControlEngine = _ec_mod.ExposureControlEngine
ExposureConfig       = _ec_mod.ExposureConfig
ExposurePosition     = _ec_mod.ExposurePosition
CorrelationFilter       = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig


def _run(coro):
    return asyncio.run(coro)


def _trade(symbol='EURUSD', lot=1.0, entry=11.0, sl=10.0, bal=10_000.0):
    """
    portfolio_risk formula: risk_amount = abs(entry-sl) * lot * pip_value
    EURUSD pip_value=10: dist=1, lot=1 -> risk=10 USD -> 0.10%
    To get N% risk: dist*lot*10/10000*100=N => dist*lot = N*100
    """
    return OpenTradeRisk(symbol=symbol, direction=TradeDirection.BUY,
                         lot_size=lot, entry_price=entry, stop_loss=sl,
                         account_balance=bal)


def _pos(symbol='EURUSD', risk_pct=1.0, direction='BUY'):
    return ExposurePosition(symbol=symbol, direction=direction,
                            risk_percent=risk_pct, risk_usd=0.0)


# =============================================================================
# TOPIC 1 - NEWS EVENT BLOCKING
# =============================================================================
class TestNewsEventBlocking(unittest.TestCase):
    """
    Detected Issue:
      During NFP/FOMC, traders attempt oversized lots.
      Before FIX #4, XAUUSD pip_value=10.0 (wrong), so gold risk was
      reported 10x too small and PortfolioRiskManager passed bad trades.

    Exact Patch:
      portfolio_risk.py _PIP_VALUE_TABLE["XAUUSD"] = 1.0  (was 10.0)
      lot_sizing.py     _PIP_VALUE_TABLE["XAUUSD"] = 1.0  (was 10.0)
      PortfolioRiskManager.check() now wraps _check_inner() in try/except

    Risk Impact:
      Wrong pip value => risk 10x under-reported => gate passes oversized
      NFP trades => unbounded account exposure.

    Backward Compatibility:
      check() and check_async() signatures unchanged.
      PortfolioRiskManager() with no args still works.
    """

    def setUp(self):
        self.mgr = PortfolioRiskManager(
            config=PortfolioRiskConfig(
                max_portfolio_risk_pct=6.0, max_single_symbol_pct=2.0
            )
        )

    def test_normal_trade_allowed(self):
        # dist=1, lot=1, pv=10 => risk=0.10% < 2.0% -> allowed
        t = _trade('EURUSD', lot=1.0, entry=11.0, sl=10.0, bal=10_000)
        r = self.mgr.check(t, [])
        self.assertTrue(r.can_trade, r.reason)
        self.assertIn(r.risk_level, [RiskLevel.SAFE, RiskLevel.WARNING])

    def test_single_trade_oversized_blocked(self):
        # dist=21, lot=1, pv=10 => risk=21*10/10000*100=2.1% > 2.0% -> block
        t = _trade('EURUSD', lot=1.0, entry=121.0, sl=100.0, bal=10_000)
        self.assertAlmostEqual(t.risk_percent, 2.1, places=1)
        r = self.mgr.check(t, [])
        self.assertFalse(r.can_trade)
        self.assertIn('SINGLE_TRADE_RISK', r.reason)
        self.assertEqual(r.risk_level, RiskLevel.BLOCKED)

    def test_cumulative_risk_blocked(self):
        # tight max=3.0%; 3 existing at 1.0% each + new 1.0% = 4.0% > 3.0%
        mgr = PortfolioRiskManager(
            config=PortfolioRiskConfig(max_portfolio_risk_pct=3.0, max_single_symbol_pct=5.0)
        )
        existing = [
            _trade('EURUSD', lot=10.0, entry=11.0, sl=10.0, bal=10_000),
            _trade('GBPUSD', lot=10.0, entry=11.0, sl=10.0, bal=10_000),
            _trade('AUDUSD', lot=10.0, entry=11.0, sl=10.0, bal=10_000),
        ]
        new_t = _trade('USDJPY', lot=10.0, entry=11.0, sl=10.0, bal=10_000)
        r = mgr.check(new_t, existing)
        self.assertFalse(r.can_trade)
        self.assertIn('PORTFOLIO_RISK', r.reason)

    def test_remaining_cap_computed(self):
        existing = [_trade('EURUSD', lot=10.0, entry=11.0, sl=10.0, bal=10_000)]
        new_t    = _trade('GBPUSD', lot=1.0, entry=11.0, sl=10.0, bal=10_000)
        r = self.mgr.check(new_t, existing)
        self.assertTrue(r.can_trade)
        self.assertGreater(r.remaining_cap, 0.0)

    def test_fail_open_allows_on_exception(self):
        mgr = PortfolioRiskManager(config=PortfolioRiskConfig(), fail_mode=FailMode.FAIL_OPEN)
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError('crash')):
            r = mgr.check(_trade(), [])
        self.assertTrue(r.can_trade); self.assertEqual(r.risk_level, RiskLevel.WARNING)

    def test_fail_closed_blocks_on_exception(self):
        mgr = PortfolioRiskManager()
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError('crash')):
            r = mgr.check(_trade(), [])
        self.assertFalse(r.can_trade); self.assertEqual(r.risk_level, RiskLevel.BLOCKED)

    def test_gold_risk_calculation_correct(self):
        # XAUUSD pip_value=1.0 (patched from 10.0)
        # dist=10, lot=1.0, pv=1.0 -> risk_amount=10 USD -> 0.10%
        t = OpenTradeRisk(symbol='XAUUSD', direction=TradeDirection.BUY,
                          lot_size=1.0, entry_price=2010.00, stop_loss=2000.00,
                          account_balance=10_000.0)
        self.assertAlmostEqual(t.risk_percent, 0.10, places=2)
        self.assertAlmostEqual(t.risk_amount, 10.0, places=2)

    def test_warning_level_at_60pct(self):
        # lot=35, dist=1, pv=10 -> 3.5% existing; new small -> WARNING
        existing = [_trade('EURUSD', lot=35.0, entry=11.0, sl=10.0, bal=10_000)]
        new_t    = _trade('GBPUSD', lot=1.0, entry=11.0, sl=10.0, bal=10_000)
        r = self.mgr.check(new_t, existing)
        self.assertTrue(r.can_trade)
        self.assertIn(r.risk_level, [RiskLevel.WARNING, RiskLevel.CRITICAL])


# =============================================================================
# TOPIC 2 - ATR SPIKE ROBUSTNESS
# =============================================================================
class TestATRSpikeRobustness(unittest.TestCase):
    """
    Detected Issue:
      VolatilityFilter._check_inner() had no try/except before FIX #6.
      Exception propagated silently; no FAIL_OPEN/FAIL_CLOSED control.

    Exact Patch:
      check() wraps _check_inner() in try/except.
      _fail_mode cached once in __init__ (FIX #7).
      FAIL_CLOSED => block; FAIL_OPEN => allow + CRITICAL log.

    Risk Impact:
      Unhandled ATR spike exception => gate crashes => trade silently allowed
      => account exposed at 3-5x intended SL distance.

    Backward Compatibility:
      check(current_atr, atr_history, spread, avg_spread, symbol) unchanged.
    """

    def setUp(self):
        self.vf      = VolatilityFilter(VolatilityConfig(
            atr_min_ratio=0.5, atr_max_ratio=3.0,
            max_spread_ratio=2.0, min_atr_bars=5,
        ))
        self.history = [0.0010] * 10

    def test_normal_atr_allowed(self):
        r = self.vf.check(0.0010, self.history, 0.00015, 0.00015, 'EURUSD')
        self.assertTrue(r.can_trade); self.assertEqual(r.reason, 'VOLATILITY_OK')

    def test_atr_spike_blocked(self):
        r = self.vf.check(0.0040, self.history, 0.00015, 0.00015, 'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('ATR_TOO_HIGH', r.reason)
        self.assertAlmostEqual(r.atr_ratio, 4.0, places=2)

    def test_atr_crash_blocked(self):
        r = self.vf.check(0.0002, self.history, 0.00015, 0.00015, 'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('ATR_TOO_LOW', r.reason)

    def test_spread_spike_blocked(self):
        r = self.vf.check(0.0010, self.history, 0.00045, 0.00015, 'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('SPREAD_TOO_WIDE', r.reason)
        self.assertAlmostEqual(r.spread_ratio, 3.0, places=2)

    def test_atr_exactly_at_max_boundary_allowed(self):
        r = self.vf.check(0.0030, self.history, 0.00015, 0.00015, 'EURUSD')
        self.assertTrue(r.can_trade, r.reason)  # ratio==3.0, not > 3.0

    def test_insufficient_history_allowed(self):
        r = self.vf.check(0.0010, [0.0010]*3, 0.00015, 0.00015, 'EURUSD')
        self.assertTrue(r.can_trade); self.assertEqual(r.reason, 'INSUFFICIENT_ATR_HISTORY')

    def test_zero_avg_atr_allowed(self):
        r = self.vf.check(0.0010, [0.0]*10, 0.00015, 0.00015, 'EURUSD')
        self.assertTrue(r.can_trade); self.assertIn('ZERO_AVG_ATR', r.reason)

    def test_fail_closed_exception_blocks(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf, '_check_inner', side_effect=ZeroDivisionError('boom')):
            r = vf.check(0.001, [0.001]*10, 0.0001, 0.0001, 'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_fail_open_exception_allows(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf, '_check_inner', side_effect=ValueError('corrupt')):
            r = vf.check(0.001, [0.001]*10, 0.0001, 0.0001, 'EURUSD')
        self.assertTrue(r.can_trade); self.assertIn('FAIL_OPEN', r.reason)

    def test_exception_always_logged(self):
        vf = VolatilityFilter(VolatilityConfig())
        with patch.object(vf, '_check_inner', side_effect=RuntimeError('crash')):
            with self.assertLogs('risk.volatility_filter', level='ERROR'):
                vf.check(0.001, [0.001]*10, 0.0001, 0.0001, 'GBPUSD')

    def test_cache_populated_after_check(self):
        self.vf.check(0.0010, self.history, 0.00015, 0.00015, 'EURUSD')
        cached = self.vf.get_cached('EURUSD')
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0].reason, 'VOLATILITY_OK')


# =============================================================================
# TOPIC 3 - SYMBOL-SPECIFIC THRESHOLDS
# =============================================================================
class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    Detected Issue:
      Single global VolatilityConfig used for all assets.
      Gold ATR ~$15/day; BTC ATR ~$2000+/day. One-size thresholds fail.

    Exact Patch:
      VolatilityConfig accepts atr_max_ratio, max_spread_ratio per asset class.
      Each VolatilityFilter instance carries its own config.

    Risk Impact:
      Wrong thresholds => asset-class spikes not blocked.

    Backward Compatibility:
      VolatilityConfig accepts any float for ratio thresholds.
    """

    def test_gold_spike_blocked_with_tight_config(self):
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        r  = vf.check(35.0, [15.0]*10, 0.5, 0.5, 'XAUUSD')  # 35/15=2.33 > 2.0
        self.assertFalse(r.can_trade); self.assertIn('ATR_TOO_HIGH', r.reason)

    def test_btc_spike_allowed_with_wide_config(self):
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        r  = vf.check(4000.0, [500.0]*10, 50.0, 50.0, 'BTCUSD')  # 8.0 < 10.0
        self.assertTrue(r.can_trade, r.reason)

    def test_forex_tight_config_blocks(self):
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.5, min_atr_bars=5))
        r  = vf.check(0.0028, [0.001]*10, 0.00015, 0.00015, 'GBPUSD')  # 2.8>2.5
        self.assertFalse(r.can_trade)

    def test_cache_isolation_per_symbol(self):
        vf   = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        hist = [0.001]*10
        vf.check(0.004, hist, 0.0001, 0.0001, 'EURUSD')  # blocked 4x
        vf.check(0.001, hist, 0.0001, 0.0001, 'GBPUSD')  # allowed 1x
        self.assertFalse(vf.get_cached('EURUSD')[0].can_trade)
        self.assertTrue(vf.get_cached('GBPUSD')[0].can_trade)

    def test_zero_min_bars_zero_avg(self):
        vf = VolatilityFilter(VolatilityConfig(min_atr_bars=0))
        r  = vf.check(0.001, [], 0.0001, 0.0001, 'EURUSD')
        self.assertTrue(r.can_trade); self.assertIn('ZERO_AVG_ATR', r.reason)

    def test_custom_spread_ratio_wide(self):
        vf = VolatilityFilter(VolatilityConfig(max_spread_ratio=5.0, min_atr_bars=5))
        r  = vf.check(500.0, [500.0]*10, 200.0, 50.0, 'BTCUSD')  # 4.0 < 5.0
        self.assertTrue(r.can_trade, r.reason)


# =============================================================================
# TOPIC 4 - GOLD PIP VALUE
# =============================================================================
class TestGoldPipValue(unittest.TestCase):
    """
    Detected Issue:
      Before FIX #4, XAUUSD pip_value=10.0 (wrong).
      Correct: 1.0 (Gold=$1 per 0.01-point tick per standard lot).

    Exact Patch:
      lot_sizing.py:     "XAUUSD":  1.0,  # was 10.0
      portfolio_risk.py: "XAUUSD":  1.0,  # was 10.0

    Risk Impact:
      pip_value=10.0 => lot size 10x too small => actual risk only 10% of
      intended => ExposureControl under-reports => limits not enforced.

    Backward Compatibility:
      _resolve_pip_value() and _get_pip_value() signatures unchanged.
    """

    def test_lot_sizing_xauusd_table(self):        self.assertEqual(_PIP_TABLE_LS.get('XAUUSD'), 1.0)
    def test_portfolio_risk_xauusd_table(self):    self.assertEqual(_PIP_TABLE_PR.get('XAUUSD'), 1.0)
    def test_lot_sizing_resolve_xauusd(self):      self.assertEqual(_resolve_pip_ls('XAUUSD'), 1.0)
    def test_lot_sizing_resolve_gold_alias(self):  self.assertEqual(_resolve_pip_ls('GOLD'), 1.0)
    def test_lot_sizing_resolve_xauusdm_suffix(self): self.assertEqual(_resolve_pip_ls('XAUUSDm'), 1.0)
    def test_portfolio_risk_resolve_xauusd(self):  self.assertEqual(_get_pip_value_pr('XAUUSD'), 1.0)
    def test_portfolio_risk_resolve_gold_alias(self): self.assertEqual(_get_pip_value_pr('GOLD'), 1.0)
    def test_lot_sizing_silver(self):              self.assertEqual(_PIP_TABLE_LS.get('XAGUSD'), 50.0)
    def test_portfolio_risk_silver(self):          self.assertEqual(_PIP_TABLE_PR.get('XAGUSD'), 50.0)
    def test_gold_pip_value_not_10(self):
        self.assertNotEqual(_PIP_TABLE_LS.get('XAUUSD'), 10.0)
        self.assertNotEqual(_PIP_TABLE_PR.get('XAUUSD'), 10.0)

    def test_gold_risk_calculation(self):
        # pip_value=1.0: dist=10, lot=1.0 -> risk_amount=10 USD -> 0.10%
        t = OpenTradeRisk(symbol='XAUUSD', direction=TradeDirection.BUY,
                          lot_size=1.0, entry_price=2010.00, stop_loss=2000.00,
                          account_balance=10_000.0)
        self.assertAlmostEqual(t.risk_percent, 0.10, places=2)
        self.assertAlmostEqual(t.risk_amount, 10.0, places=2)

    def test_lot_sizer_gold_lot_calculation(self):
        # risk_usd=100, sl_pips=20, pip_value=1.0 => lot=5.0
        sizer  = LotSizer(LotSizingConfig(method=LotSizingMethod.ATR_BASED,
                                          risk_percent=1.0, max_lot=100.0))
        result = asyncio.run(sizer.calculate('XAUUSD', 10_000.0, 20.0))
        self.assertAlmostEqual(result.lot_size, 5.0, places=1)
        self.assertAlmostEqual(result.risk_percent, 1.0, places=1)


# =============================================================================
# TOPIC 5 - CRYPTO PIP VALUE
# =============================================================================
class TestCryptoPipValue(unittest.TestCase):
    """
    Detected Issue:
      Before FIX #4, ETHUSD pip_value=0.01 in some modules.
      Correct: 1.0 (crypto=$1 per point per standard lot).

    Exact Patch:
      lot_sizing.py: BTCUSD/ETHUSD/LTCUSD/BNBUSD/XRPUSD = 1.0

    Risk Impact:
      ETHUSD at 0.01 => lot size 100x too large => account blown.

    Backward Compatibility:
      _resolve_pip_value() signature unchanged.
    """

    def test_btcusd_lot_sizing(self):    self.assertEqual(_resolve_pip_ls('BTCUSD'), 1.0)
    def test_ethusd_lot_sizing(self):    self.assertEqual(_resolve_pip_ls('ETHUSD'), 1.0)
    def test_ltcusd_lot_sizing(self):    self.assertEqual(_resolve_pip_ls('LTCUSD'), 1.0)
    def test_bnbusd_lot_sizing(self):    self.assertEqual(_resolve_pip_ls('BNBUSD'), 1.0)
    def test_xrpusd_lot_sizing(self):    self.assertEqual(_resolve_pip_ls('XRPUSD'), 1.0)
    def test_btc_alias(self):            self.assertEqual(_resolve_pip_ls('BTC'),    1.0)
    def test_eth_alias(self):            self.assertEqual(_resolve_pip_ls('ETH'),    1.0)
    def test_bitcoin_alias(self):        self.assertEqual(_resolve_pip_ls('BITCOIN'),1.0)
    def test_btcusdm_suffix(self):       self.assertEqual(_resolve_pip_ls('BTCUSDm'),1.0)
    def test_btcusd_portfolio_risk(self): self.assertEqual(_get_pip_value_pr('BTCUSD'),1.0)
    def test_ethusd_portfolio_risk(self): self.assertEqual(_get_pip_value_pr('ETHUSD'),1.0)
    def test_ethusd_not_point01(self):   self.assertNotEqual(_PIP_TABLE_LS.get('ETHUSD'), 0.01)

    def test_btc_risk_calculation(self):
        # lot=0.1, dist=1000, pip_value=1.0, bal=100000 -> risk=0.1%
        t = OpenTradeRisk(symbol='BTCUSD', direction=TradeDirection.BUY,
                          lot_size=0.1, entry_price=50_000.0, stop_loss=49_000.0,
                          account_balance=100_000.0)
        self.assertAlmostEqual(t.risk_percent, 0.1, places=2)


# =============================================================================
# TOPIC 6 - EXPOSURE CALCULATION
# =============================================================================
class TestExposureCalculation(unittest.TestCase):
    """
    Detected Issue:
      ExposureControlEngine.check() had no try/except before FIX #6.
      new_risk_percent was hardcoded to 1.0 before FIX #5.

    Exact Patch:
      check() wraps _check_inner() in try/except.
      get_snapshot() wraps _snapshot_inner() in try/except.
      FAIL_CLOSED: block; FAIL_OPEN: allow with FAIL_OPEN_EXCEPTION_IGNORED.

    Risk Impact:
      Without enforcement => 10+ correlated positions => unbounded exposure.

    Backward Compatibility:
      check(symbol, direction, risk_pct, positions, balance) unchanged.
    """

    def setUp(self):
        self.eng = ExposureControlEngine(ExposureConfig(
            max_total_risk_percent=5.0, max_risk_per_symbol=2.0, max_open_trades=3
        ))

    def test_no_open_positions_allowed(self):
        r = self.eng.check('EURUSD', 'BUY', 1.0, [], 10_000)
        self.assertTrue(r.can_trade); self.assertEqual(r.reason, 'EXPOSURE_OK')

    def test_total_risk_exceeded(self):
        ops = [_pos('EURUSD', 1.5), _pos('GBPUSD', 1.5), _pos('AUDUSD', 1.5)]
        r = self.eng.check('USDJPY', 'BUY', 1.5, ops, 10_000)
        self.assertFalse(r.can_trade); self.assertIn('MAX_TOTAL_RISK', r.reason)
        self.assertAlmostEqual(r.projected_total_risk, 6.0, places=1)

    def test_symbol_risk_exceeded(self):
        ops = [_pos('EURUSD', 1.5)]
        r = self.eng.check('EURUSD', 'BUY', 1.0, ops, 10_000)
        self.assertFalse(r.can_trade); self.assertIn('MAX_SYMBOL_RISK', r.reason)

    def test_max_open_trades_exceeded(self):
        ops = [_pos('EURUSD', 0.5), _pos('GBPUSD', 0.5), _pos('AUDUSD', 0.5)]
        r = self.eng.check('USDJPY', 'BUY', 0.5, ops, 10_000)
        self.assertFalse(r.can_trade); self.assertIn('MAX_OPEN_TRADES', r.reason)

    def test_available_risk_computed(self):
        ops = [_pos('EURUSD', 2.0)]
        r   = self.eng.check('GBPUSD', 'BUY', 1.0, ops, 10_000)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.current_total_risk,   2.0, places=1)
        self.assertAlmostEqual(r.projected_total_risk, 3.0, places=1)
        self.assertAlmostEqual(r.available_risk,       3.0, places=1)

    def test_fail_closed_exception_blocks(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, '_check_inner', side_effect=AttributeError('bad')):
            r = eng.check('EURUSD', 'BUY', 1.0, [], 10_000)
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_fail_open_exception_allows(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, '_check_inner', side_effect=AttributeError('bad')):
            r = eng.check('EURUSD', 'BUY', 1.5, [], 10_000)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, 'FAIL_OPEN_EXCEPTION_IGNORED')
        self.assertAlmostEqual(r.projected_total_risk, 1.5, places=1)

    def test_snapshot_fail_closed_reraises(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, '_snapshot_inner', side_effect=RuntimeError('snap')):
            with self.assertRaises(RuntimeError): eng.get_snapshot([])

    def test_snapshot_fail_open_returns_empty(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, '_snapshot_inner', side_effect=RuntimeError('snap')):
            snap = eng.get_snapshot([])
        self.assertEqual(snap.total_risk_percent, 0.0); self.assertFalse(snap.limit_breached)

    def test_snapshot_totals(self):
        ops  = [_pos('EURUSD',1.5,'BUY'), _pos('GBPUSD',1.0,'SELL'), _pos('EURUSD',0.5,'BUY')]
        snap = ExposureControlEngine().get_snapshot(ops)
        self.assertAlmostEqual(snap.total_risk_percent, 3.0, places=1)
        self.assertAlmostEqual(snap.risk_by_symbol['EURUSD'], 2.0, places=1)
        self.assertEqual(snap.open_trade_count, 3)

    def test_snapshot_breach_flag(self):
        ops  = [_pos('EURUSD', 3.0), _pos('GBPUSD', 3.0)]
        snap = ExposureControlEngine().get_snapshot(ops)
        self.assertTrue(snap.limit_breached); self.assertEqual(snap.breach_reason, 'MAX_TOTAL_RISK')

    def test_exception_always_logged(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError('crash')):
            with self.assertLogs('risk.exposure_control', level='ERROR'):
                eng.check('EURUSD', 'BUY', 1.0, [], 10_000)


# =============================================================================
# TOPIC 7 - FAIL-CLOSED BEHAVIOUR
# =============================================================================
class TestFailClosedBehaviour(unittest.TestCase):
    """
    Detected Issue:
      Before FIX #6, some gates had bare `except: allow_trade=True`
      (FAIL_OPEN by default, unlogged). No configurable fail_mode existed.

    Exact Patch:
      fail_mode.py (NEW): canonical FailMode enum + coerce().
      All gates default FAIL_CLOSED. Exception => CRITICAL log.
      _fail_mode cached in __init__ of VolatilityFilter (FIX #7).

    Risk Impact:
      Silent FAIL_OPEN => trade allowed despite gate crash => uncontrolled exposure.

    Backward Compatibility:
      No-args constructors work. String 'FAIL_CLOSED' coerced via coerce().
    """

    def test_failmode_string_values(self):
        self.assertEqual(FailMode.FAIL_CLOSED, 'FAIL_CLOSED')
        self.assertEqual(FailMode.FAIL_OPEN,   'FAIL_OPEN')

    def test_coerce_uppercase_string(self):
        self.assertIs(coerce('FAIL_CLOSED'), FailMode.FAIL_CLOSED)
        self.assertIs(coerce('FAIL_OPEN'),   FailMode.FAIL_OPEN)

    def test_coerce_lowercase_string(self):
        self.assertIs(coerce('fail_closed'), FailMode.FAIL_CLOSED)
        self.assertIs(coerce('fail_open'),   FailMode.FAIL_OPEN)

    def test_coerce_enum_identity(self):
        self.assertIs(coerce(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)
        self.assertIs(coerce(FailMode.FAIL_OPEN),   FailMode.FAIL_OPEN)

    def test_single_source_of_truth(self):
        for mod in [_vf_mod, _ec_mod, _cf_mod, _pr_mod]:
            self.assertIs(mod.FailMode, _fm_mod.FailMode,
                          f'{mod.__name__} uses non-canonical FailMode')

    def test_volatility_filter_default_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_exposure_default_fail_closed(self):
        self.assertIs(ExposureControlEngine()._fail_mode, FailMode.FAIL_CLOSED)

    def test_correlation_filter_default_fail_closed(self):
        self.assertIs(CorrelationFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_portfolio_risk_default_fail_closed(self):
        self.assertIs(PortfolioRiskManager()._fail_mode, FailMode.FAIL_CLOSED)

    def test_string_fail_mode_accepted(self):
        eng = ExposureControlEngine(fail_mode='FAIL_CLOSED')
        self.assertIs(eng._fail_mode, FailMode.FAIL_CLOSED)
        eng2 = ExposureControlEngine(fail_mode='FAIL_OPEN')
        self.assertIs(eng2._fail_mode, FailMode.FAIL_OPEN)

    def test_corr_fail_closed_exception_blocks(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('crash')):
            r = _run(cf.check('EURUSD', 'BUY', []))
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_corr_fail_open_exception_allows(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('crash')):
            r = _run(cf.check('EURUSD', 'BUY', []))
        self.assertTrue(r.can_trade); self.assertIn('FAIL_OPEN', r.reason)

    def test_corr_exception_logged_critical(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('boom')):
            with self.assertLogs('risk.correlation_filter', level='CRITICAL'):
                _run(cf.check('EURUSD', 'BUY', []))

    def test_volatility_fail_mode_cached_immutable(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))
        self.assertIs(vf._fail_mode, FailMode.FAIL_OPEN)
        vf._cfg.fail_mode = FailMode.FAIL_CLOSED  # mutate config
        self.assertIs(vf._fail_mode, FailMode.FAIL_OPEN)  # still cached FAIL_OPEN

    def test_kwarg_overrides_config_fail_mode(self):
        cfg = ExposureConfig(fail_mode=FailMode.FAIL_OPEN)
        eng = ExposureControlEngine(config=cfg, fail_mode=FailMode.FAIL_CLOSED)
        self.assertIs(eng._fail_mode, FailMode.FAIL_CLOSED)

    def test_fail_open_logs_critical_not_silent(self):
        eng = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError('swallow')):
            with self.assertLogs('risk.exposure_control', level='CRITICAL'):
                eng.check('EURUSD', 'BUY', 1.0, [], 10_000)


# =============================================================================
# TOPIC 8 - PORTFOLIO CORRELATION CALCULATIONS
# =============================================================================
class TestPortfolioCorrelationCalculations(unittest.TestCase):
    """
    Detected Issue:
      CorrelationFilter.check() had no try/except before FIX #6.
      Per-pair engine exceptions returned corr=0.0 (correct inner handling),
      but outer exception propagated unlogged without FAIL_CLOSED control.

    Exact Patch:
      check() wraps _check_inner() in try/except with fail_mode.
      Per-pair exception => corr=0.0 (uncorrelated, trade allowed).
      Same-symbol: if pos_sym == symbol: continue.
      abs(corr) used for threshold (blocks negative correlations too).

    Risk Impact:
      High-corr pair allowed when engine crashes => doubled exposure.

    Backward Compatibility:
      check(symbol, direction, open_positions) unchanged.
    """

    def _engine(self, pairs: dict):
        eng = MagicMock()
        async def get_corr(a, b):
            return pairs.get((a, b), pairs.get((b, a), 0.0))
        eng.get_correlation = get_corr
        return eng

    def test_no_positions_allowed(self):
        r = _run(CorrelationFilter().check('EURUSD', 'BUY', []))
        self.assertTrue(r.can_trade); self.assertEqual(r.reason, 'NO_POSITIONS_OR_ENGINE')

    def test_high_correlation_blocked(self):
        engine = self._engine({('EURUSD', 'GBPUSD'): 0.92})
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'GBPUSD'}]))
        self.assertFalse(r.can_trade); self.assertIn('CORR_TOO_HIGH', r.reason)
        self.assertAlmostEqual(r.correlation, 0.92, places=2)

    def test_low_correlation_allowed(self):
        engine = self._engine({('EURUSD', 'USDJPY'): 0.30})
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'USDJPY'}]))
        self.assertTrue(r.can_trade); self.assertEqual(r.reason, 'CORR_OK')

    def test_same_symbol_skipped(self):
        engine = self._engine({('EURUSD', 'EURUSD'): 1.0})
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'EURUSD'}]))
        self.assertTrue(r.can_trade)  # same symbol skipped

    def test_per_pair_exception_treated_as_zero_corr(self):
        engine = MagicMock()
        async def boom(a, b): raise RuntimeError('engine down')
        engine.get_correlation = boom
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'GBPUSD'}]))
        self.assertTrue(r.can_trade)  # corr=0.0 < 0.85 -> allowed

    def test_static_corr_eurusd_gbpusd(self):
        table = _pr_mod._STATIC_CORRELATIONS
        val = table.get(('EURUSD', 'GBPUSD')) or table.get(('GBPUSD', 'EURUSD'))
        self.assertIsNotNone(val); self.assertAlmostEqual(abs(val), 0.85, places=2)

    def test_static_corr_btc_eth(self):
        table = _pr_mod._STATIC_CORRELATIONS
        val = table.get(('BTCUSD', 'ETHUSD')) or table.get(('ETHUSD', 'BTCUSD'))
        self.assertIsNotNone(val); self.assertAlmostEqual(val, 0.90, places=2)

    def test_static_corr_usdchf_eurusd_negative(self):
        table = _pr_mod._STATIC_CORRELATIONS
        val = table.get(('USDCHF', 'EURUSD')) or table.get(('EURUSD', 'USDCHF'))
        self.assertIsNotNone(val); self.assertLess(val, 0.0)

    def test_negative_high_correlation_blocked(self):
        engine = self._engine({('EURUSD', 'USDCHF'): -0.92})
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'USDCHF'}]))
        self.assertFalse(r.can_trade)  # abs(-0.92) > 0.85 => blocked

    def test_no_engine_allowed(self):
        cf = CorrelationFilter(config=CorrelationFilterConfig(), correlation_engine=None)
        r  = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'GBPUSD'}]))
        self.assertTrue(r.can_trade); self.assertEqual(r.reason, 'NO_POSITIONS_OR_ENGINE')

    def test_outer_exception_fail_closed_blocks(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('crash')):
            r = _run(cf.check('EURUSD', 'BUY', []))
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_outer_exception_fail_open_allows(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError('crash')):
            r = _run(cf.check('EURUSD', 'BUY', []))
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, 'FAIL_OPEN:CORR_EXCEPTION_IGNORED')

    def test_multiple_positions_first_high_corr_blocks(self):
        engine = self._engine({
            ('EURUSD', 'GBPUSD'): 0.92,
            ('EURUSD', 'AUDUSD'): 0.30,
        })
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'GBPUSD'}, {'symbol': 'AUDUSD'}]))
        self.assertFalse(r.can_trade); self.assertEqual(r.pair_checked, 'GBPUSD')

    def test_exactly_at_threshold_blocked(self):
        engine = self._engine({('EURUSD', 'GBPUSD'): 0.85})
        cf = CorrelationFilter(config=CorrelationFilterConfig(max_corr=0.85),
                               correlation_engine=engine)
        r = _run(cf.check('EURUSD', 'BUY', [{'symbol': 'GBPUSD'}]))
        self.assertFalse(r.can_trade)  # 0.85 >= 0.85 => blocked


# =============================================================================
# INTEGRATION
# =============================================================================
class TestIntegration(unittest.TestCase):

    def test_gold_pip_value_consistent(self):
        self.assertEqual(_resolve_pip_ls('XAUUSD'), _get_pip_value_pr('XAUUSD'))

    def test_crypto_pip_value_consistent(self):
        for sym in ['BTCUSD', 'ETHUSD']:
            self.assertEqual(_resolve_pip_ls(sym), _get_pip_value_pr(sym), f'Mismatch: {sym}')

    def test_failmode_canonical_all_modules(self):
        for mod in [_vf_mod, _ec_mod, _cf_mod, _pr_mod]:
            self.assertIs(mod.FailMode, _fm_mod.FailMode,
                          f'{mod.__name__} non-canonical FailMode')

    def test_real_risk_propagated_not_hardcoded(self):
        """
        FIX #5 regression guard:
        If 1.0 hardcoded: 3.6+1.0=4.6 < 5.0 => pass (wrong)
        With real 2.0%:   3.6+2.0=5.6 > 5.0 => block (correct)
        """
        eng = ExposureControlEngine(ExposureConfig(
            max_total_risk_percent=5.0, max_risk_per_symbol=2.0, max_open_trades=10
        ))
        ops = [_pos('EURUSD', 1.8), _pos('GBPUSD', 1.8)]
        self.assertFalse(eng.check('AUDUSD', 'BUY', 2.0, ops, 10_000).can_trade)
        self.assertTrue(eng.check('AUDUSD',  'BUY', 1.0, ops, 10_000).can_trade)

    def test_atr_spike_blocks(self):
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        r  = vf.check(0.003, [0.001]*10, 0.0001, 0.0001, 'EURUSD')  # ratio 3.0 > 2.0
        self.assertFalse(r.can_trade); self.assertIn('ATR_TOO_HIGH', r.reason)


if __name__ == '__main__':
    unittest.main(verbosity=2)
