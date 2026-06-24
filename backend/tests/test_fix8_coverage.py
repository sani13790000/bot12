"""
FIX #8 - TEST COVERAGE  (production-ready, 107 tests, 8 topics)
Verified against actual production interfaces from GitHub.
"""
from __future__ import annotations
import asyncio, importlib.util, sys, types, unittest, os
from unittest.mock import AsyncMock, MagicMock, patch

# bootstrap backend.risk.* from local .py files
_HERE = os.path.dirname(os.path.abspath(__file__))
for _pkg in ('backend', 'backend.risk'):
    if _pkg not in sys.modules:
        _m = types.ModuleType(_pkg); _m.__path__ = [_HERE]; sys.modules[_pkg] = _m

for _pkg_name, _stem in {
    'backend.risk.fail_mode':         'fail_mode',
    'backend.risk.volatility_filter': 'volatility_filter',
    'backend.risk.portfolio_risk':    'portfolio_risk',
    'backend.risk.correlation_filter':'correlation_filter',
    'backend.risk.exposure_control':  'exposure_control',
    'backend.risk.lot_sizing':        'lot_sizing',
}.items():
    if _pkg_name not in sys.modules:
        _spec = importlib.util.spec_from_file_location(_pkg_name, os.path.join(_HERE, f'{_stem}.py'))
        _mod  = importlib.util.module_from_spec(_spec)
        sys.modules[_pkg_name] = _mod
        _spec.loader.exec_module(_mod)

import backend.risk.fail_mode          as _fm_mod
import backend.risk.volatility_filter  as _vf_mod
import backend.risk.portfolio_risk     as _pr_mod
import backend.risk.correlation_filter as _cf_mod
import backend.risk.exposure_control   as _ec_mod
import backend.risk.lot_sizing         as _ls_mod

FailMode              = _fm_mod.FailMode
coerce_fm             = _fm_mod.coerce
VolatilityFilter      = _vf_mod.VolatilityFilter
VolatilityConfig      = _vf_mod.VolatilityConfig
OpenTradeRisk         = _pr_mod.OpenTradeRisk
PortfolioRiskConfig   = _pr_mod.PortfolioRiskConfig
PortfolioRiskManager  = _pr_mod.PortfolioRiskManager
CorrelationFilter     = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig
ExposureControlEngine = _ec_mod.ExposureControlEngine
ExposureConfig        = _ec_mod.ExposureConfig
ExposurePosition      = _ec_mod.ExposurePosition
LotSizer              = _ls_mod.LotSizer
LotSizingConfig       = _ls_mod.LotSizingConfig


def _otr(symbol, direction, lot, entry, sl, balance=10_000.0):
    return OpenTradeRisk(symbol=symbol, direction=direction, lot_size=lot,
                         entry_price=entry, stop_loss=sl, account_balance=balance)

def _ep(symbol, risk_pct, direction="BUY"):
    return ExposurePosition(symbol=symbol, risk_percent=risk_pct, direction=direction)

def _mock_engine(corr_map):
    eng = MagicMock()
    async def _get(s1, s2):
        return corr_map.get((s1,s2), corr_map.get((s2,s1), 0.0))
    eng.get_correlation = AsyncMock(side_effect=_get)
    return eng

def _sizer(risk_pct=1.0):
    return LotSizer(LotSizingConfig(risk_percent=risk_pct, lot_step=0.01,
                                    min_lot=0.01, max_lot=10_000.0))


# ============================================================
# TOPIC 1 - News Event Blocking (9 tests)
# ============================================================
class TestNewsEventBlocking(unittest.TestCase):
    """
    ISSUE: pip_value errors and missing try/except allowed over-leveraged
    trades to pass risk gates during news events.

    FORMULA: risk_pct = abs(entry-sl) * lot * pip_value / balance * 100
    EURUSD pip=10: lot=2001, dist=0.01 -> 2.001% > 2.0% -> BLOCKED

    PATCH: pip tables corrected; try/except added to all check() methods.
    BACKWARD COMPAT: check()/check_async() signatures unchanged.
    """

    def setUp(self):
        self.mgr = PortfolioRiskManager()

    def test_single_trade_risk_blocked_above_limit(self):
        """lot=2001,dist=0.01,pip=10 -> 2.001% > 2.0% -> SINGLE_TRADE_RISK."""
        t = _otr("EURUSD", "BUY", 2001, 1.10, 1.09)
        r = self.mgr.check(t, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)

    def test_single_trade_risk_allowed_below_limit(self):
        """lot=1500,dist=0.01,pip=10 -> 1.5% < 2.0% -> allowed."""
        t = _otr("EURUSD", "BUY", 1500, 1.10, 1.09)
        r = self.mgr.check(t, [])
        self.assertTrue(r.can_trade)

    def test_portfolio_risk_blocked(self):
        """5 existing @ 1.0% = 5.0%; new 1.5% -> 6.5% > 6.0% -> PORTFOLIO_RISK."""
        existing = [_otr("GBPUSD", "BUY", 1000, 1.30, 1.29)] * 5
        new_t    = _otr("NZDUSD", "BUY", 1500, 0.65, 0.64)
        r = self.mgr.check(new_t, existing)
        self.assertFalse(r.can_trade)
        self.assertIn("PORTFOLIO_RISK", r.reason)

    def test_portfolio_risk_ok_within_limit(self):
        """Single 1.0% trade within 6.0% limit -> allowed."""
        t = _otr("EURUSD", "BUY", 1000, 1.10, 1.09)
        r = self.mgr.check(t, [])
        self.assertTrue(r.can_trade)

    def test_risk_pct_formula_correct(self):
        """EURUSD lot=1,dist=0.01,pip=10,bal=10000 -> risk=0.001%."""
        t = _otr("EURUSD", "BUY", 1, 1.10, 1.09)
        self.assertAlmostEqual(t.risk_percent, 0.001, places=5)

    def test_gold_trade_risk_correct_pip_value(self):
        """XAUUSD pip=1.0 (FIX#4): dist=210,lot=1,bal=10k -> 2.1%."""
        t = _otr("XAUUSD", "BUY", 1, 2210, 2000, 10_000)
        self.assertAlmostEqual(t.risk_percent, 2.1, places=2)

    def test_gold_risk_not_inflated_by_ten(self):
        """pip=1.0 gives <5% risk for dist=210 lot=1 (would be 21% if pip=10)."""
        t = _otr("XAUUSD", "BUY", 1, 2210, 2000, 10_000)
        self.assertLess(t.risk_percent, 5.0)

    def test_gold_news_spike_blocked(self):
        """XAUUSD dist=210,lot=1,pip=1.0 -> 2.1% > 2.0% -> SINGLE_TRADE_RISK."""
        t = _otr("XAUUSD", "BUY", 1, 2210, 2000, 10_000)
        r = self.mgr.check(t, [])
        self.assertFalse(r.can_trade)
        self.assertIn("SINGLE_TRADE_RISK", r.reason)

    def test_check_async_matches_check(self):
        """check_async() (no lot_sizer) returns same can_trade as check()."""
        mgr = PortfolioRiskManager()
        t = _otr("EURUSD", "BUY", 1000, 1.10, 1.09)
        r_sync  = mgr.check(t, [])
        r_async = asyncio.run(mgr.check_async(t, []))
        self.assertEqual(r_sync.can_trade, r_async.can_trade)
        self.assertAlmostEqual(r_sync.new_risk_pct, r_async.new_risk_pct, places=5)


# ============================================================
# TOPIC 2 - ATR Spike Robustness (11 tests)
# ============================================================
class TestATRSpikeRobustness(unittest.TestCase):
    """
    ISSUE: VolatilityFilter.check() had no try/except before FIX #6.
    avg_atr=0 -> ZeroDivisionError -> propagate -> gate crashed -> trade allowed.

    PRODUCTION: atr_min_ratio=0.5, atr_max_ratio=3.0, max_spread_ratio=2.0.
    CONDITIONS: STRICTLY > for high, STRICTLY < for low.

    PATCH: try/except; FAIL_CLOSED blocks, FAIL_OPEN allows.
    BACKWARD COMPAT: check(atr, history, spread, avg_spread, symbol) unchanged.
    """

    def setUp(self):
        self.vf      = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        self.history = [0.001] * 20

    def test_atr_ratio_too_high_blocked(self):
        """ratio=4.0 > 3.0 -> ATR_TOO_HIGH blocked."""
        r = self.vf.check(0.004, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_atr_ratio_at_max_boundary_allowed(self):
        """ratio=3.0 exactly is allowed (STRICTLY >)."""
        r = self.vf.check(0.003, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.atr_ratio, 3.0, places=3)

    def test_atr_ratio_too_low_blocked(self):
        """ratio=0.3 < 0.5 -> ATR_TOO_LOW."""
        r = self.vf.check(0.0003, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_LOW", r.reason)

    def test_atr_ratio_at_min_boundary_allowed(self):
        """ratio=0.5 exactly is allowed (STRICTLY <)."""
        r = self.vf.check(0.0005, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_spread_too_wide_blocked(self):
        """spread_ratio=3.0 > 2.0 -> SPREAD_TOO_WIDE."""
        r = self.vf.check(0.001, self.history, 0.0006, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD_TOO_WIDE", r.reason)

    def test_normal_conditions_allowed(self):
        r = self.vf.check(0.001, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_too_few_bars_allowed(self):
        """Fewer bars than min_atr_bars -> insufficient data -> allowed."""
        vf = VolatilityFilter(VolatilityConfig(min_atr_bars=20))
        r  = vf.check(0.004, [0.001]*5, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_fail_closed_on_exception(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_CLOSED, min_atr_bars=5))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("test")):
            r = vf.check(0.001, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_on_exception(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN, min_atr_bars=5))
        with patch.object(vf, '_check_inner', side_effect=RuntimeError("test")):
            r = vf.check(0.001, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_result_has_atr_ratio(self):
        r = self.vf.check(0.002, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(hasattr(r, 'atr_ratio'))
        self.assertAlmostEqual(r.atr_ratio, 2.0, places=3)

    def test_cache_updated_after_success(self):
        self.vf.check(0.001, self.history, 0.0002, 0.0002, "EURUSD")
        self.assertIsNotNone(self.vf.get_cached("EURUSD"))


# ============================================================
# TOPIC 3 - Symbol-Specific Thresholds (7 tests)
# ============================================================
class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    ISSUE: One global atr_max_ratio=3.0 wrong for all assets.
    BTC (ATR 8x avg) -> always blocked. Gold (tight) -> missed extremes.
    PATCH: Per-asset VolatilityConfig instances.
    BACKWARD COMPAT: VolatilityConfig has defaults for all fields.
    """

    def test_gold_tight_blocks_spike(self):
        """Gold max_ratio=2.0: ratio=7/3=2.33 > 2.0 -> ATR_TOO_HIGH."""
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        r  = vf.check(7.0, [3.0]*10, 0.5, 0.5, "XAUUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("ATR_TOO_HIGH", r.reason)

    def test_gold_tight_allows_normal(self):
        """Gold max_ratio=2.0: ratio=4/3=1.33 < 2.0 -> allowed."""
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=2.0, min_atr_bars=5))
        r  = vf.check(4.0, [3.0]*10, 0.5, 0.5, "XAUUSD")
        self.assertTrue(r.can_trade)

    def test_btc_loose_allows_high_atr(self):
        """BTC max_ratio=10.0: ratio=8.0 < 10.0 -> allowed."""
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        r  = vf.check(8000.0, [1000.0]*10, 50.0, 50.0, "BTCUSD")
        self.assertTrue(r.can_trade)

    def test_btc_loose_blocks_extreme(self):
        """BTC max_ratio=10.0: ratio=11.0 > 10.0 -> ATR_TOO_HIGH."""
        vf = VolatilityFilter(VolatilityConfig(atr_max_ratio=10.0, min_atr_bars=5))
        r  = vf.check(11000.0, [1000.0]*10, 50.0, 50.0, "BTCUSD")
        self.assertFalse(r.can_trade)

    def test_global_default_blocks_4x_atr(self):
        """Default max_ratio=3.0: ratio=4.0 -> blocked."""
        vf = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        r  = vf.check(0.004, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_per_symbol_cache_isolation(self):
        vf = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        h  = [0.001]*10
        vf.check(0.001, h, 0.0002, 0.0002, "EURUSD")
        vf.check(0.001, h, 0.0002, 0.0002, "GBPUSD")
        self.assertIsNotNone(vf.get_cached("EURUSD"))
        self.assertIsNotNone(vf.get_cached("GBPUSD"))
        self.assertIsNone(vf.get_cached("AUDUSD"))

    def test_independent_instances_no_shared_cache(self):
        vf1 = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        vf2 = VolatilityFilter(VolatilityConfig(min_atr_bars=5))
        vf1.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertIsNone(vf2.get_cached("EURUSD"))


# ============================================================
# TOPIC 4 - Gold Pip Value (12 tests)
# ============================================================
class TestGoldPipValue(unittest.TestCase):
    """
    ISSUE (FIX #4): XAUUSD pip=10.0 in both modules (10x wrong).
    Correct: Gold pip = $0.01/oz * 100oz = $1.00 per pip per lot.
    RISK: pip=10 -> lot_sizer 10x undersized -> 10% intended risk.
    PATCH: _PIP_VALUE_TABLE["XAUUSD"] = 1.0 in both modules.
    BACKWARD COMPAT: _get_pip_value(), _resolve_pip_value() unchanged.
    """

    def test_ls_xauusd_pip_is_one(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_pr_xauusd_pip_is_one(self):
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_gold_alias(self):
        self.assertEqual(LotSizer().get_pip_value("GOLD"), 1.0)

    def test_xauusdm_suffix(self):
        self.assertEqual(LotSizer().get_pip_value("XAUUSDm"), 1.0)

    def test_xauusdpro_suffix(self):
        self.assertEqual(LotSizer().get_pip_value("XAUUSDpro"), 1.0)

    def test_silver_pip_is_fifty(self):
        self.assertEqual(LotSizer().get_pip_value("XAGUSD"), 50.0)

    def test_silver_alias(self):
        self.assertEqual(LotSizer().get_pip_value("SILVER"), 50.0)

    def test_gold_lot_size(self):
        """1% risk, 50-pip SL: raw_lot=100/(50*1.0)=2.0 (not 0.2 with pip=10)."""
        r = asyncio.run(_sizer().calculate("XAUUSD", 10_000, 50))
        self.assertAlmostEqual(r.lot_size, 2.0, places=2)

    def test_gold_risk_pct(self):
        """LotSizer returns 1.0% risk for XAUUSD 50-pip SL."""
        r = asyncio.run(_sizer().calculate("XAUUSD", 10_000, 50))
        self.assertAlmostEqual(r.risk_percent, 1.0, places=2)

    def test_otr_gold_risk_correct(self):
        """OpenTradeRisk: XAUUSD dist=210,lot=1 -> 2.1% (not 21% with pip=10)."""
        t = _otr("XAUUSD", "BUY", 1, 2210, 2000, 10_000)
        self.assertAlmostEqual(t.risk_percent, 2.1, places=2)

    def test_otr_gold_not_inflated(self):
        t = _otr("XAUUSD", "BUY", 1, 2210, 2000, 10_000)
        self.assertLess(t.risk_percent, 5.0)

    def test_pip_value_source_recorded(self):
        t = _otr("XAUUSD", "BUY", 1, 2210, 2000, 10_000)
        self.assertTrue(hasattr(t, 'pip_value_source'))
        self.assertIsNotNone(t.pip_value_source)


# ============================================================
# TOPIC 5 - Crypto Pip Value (12 tests)
# ============================================================
class TestCryptoPipValue(unittest.TestCase):
    """
    ISSUE: ETHUSD pip_value wrong -> lot 100x too large -> account blown.
    PATCH: BTC/ETH/LTC/BNB/XRP = 1.0.
    BACKWARD COMPAT: _resolve_pip_value() unchanged.
    """

    def _pv(self, sym): return LotSizer().get_pip_value(sym)

    def test_btcusd(self): self.assertEqual(self._pv("BTCUSD"), 1.0)
    def test_ethusd(self): self.assertEqual(self._pv("ETHUSD"), 1.0)
    def test_ltcusd(self): self.assertEqual(self._pv("LTCUSD"), 1.0)
    def test_bnbusd(self): self.assertEqual(self._pv("BNBUSD"), 1.0)
    def test_xrpusd(self): self.assertEqual(self._pv("XRPUSD"), 1.0)
    def test_btc_alias(self):     self.assertEqual(self._pv("BTC"),     1.0)
    def test_bitcoin_alias(self): self.assertEqual(self._pv("BITCOIN"), 1.0)
    def test_eth_alias(self):     self.assertEqual(self._pv("ETH"),     1.0)
    def test_btcusdm_suffix(self):self.assertEqual(self._pv("BTCUSDm"), 1.0)

    def test_btc_lot_correct(self):
        """1% risk, 500-pip SL: lot=100/(500*1.0)=0.20."""
        r = asyncio.run(_sizer().calculate("BTCUSD", 10_000, 500))
        self.assertAlmostEqual(r.lot_size, 0.20, places=2)

    def test_eth_lot_correct(self):
        """1% risk, 200-pip SL: lot=100/(200*1.0)=0.50."""
        r = asyncio.run(_sizer().calculate("ETHUSD", 10_000, 200))
        self.assertAlmostEqual(r.lot_size, 0.50, places=2)

    def test_table_has_all_five(self):
        for sym in ("BTCUSD","ETHUSD","LTCUSD","BNBUSD","XRPUSD"):
            self.assertIn(sym, _ls_mod._PIP_VALUE_TABLE)


# ============================================================
# TOPIC 6 - Exposure Calculation (14 tests)
# ============================================================
class TestExposureCalculation(unittest.TestCase):
    """
    ISSUE: check() no try/except; corrupt pos -> propagate -> gate bypass.
    THREE LIMITS: MAX_TOTAL_RISK(5%), MAX_SYMBOL_RISK(2%), MAX_OPEN_TRADES(5).
    PATCH: try/except wraps _check_inner().
    BACKWARD COMPAT: check(sym,dir,risk,pos,balance) unchanged.
    """

    def setUp(self):
        self.cfg = ExposureConfig(max_total_risk_percent=5.0,
                                  max_risk_per_symbol=2.0, max_open_trades=5)
        self.eng = ExposureControlEngine(config=self.cfg)

    def test_max_total_risk_blocked(self):
        existing = [_ep("EURUSD",1.0),_ep("GBPUSD",1.0),
                    _ep("USDJPY",1.0),_ep("AUDUSD",1.0)]
        r = self.eng.check("NZDUSD","BUY",1.5,existing,10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_TOTAL_RISK", r.reason)

    def test_max_total_risk_boundary_allowed(self):
        existing = [_ep("EURUSD",1.0),_ep("GBPUSD",1.0),
                    _ep("USDJPY",1.0),_ep("AUDUSD",1.0)]
        r = self.eng.check("NZDUSD","BUY",1.0,existing,10_000)
        self.assertTrue(r.can_trade)

    def test_max_symbol_risk_blocked(self):
        r = self.eng.check("EURUSD","BUY",1.0,[_ep("EURUSD",1.5)],10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)

    def test_max_symbol_risk_boundary_allowed(self):
        r = self.eng.check("EURUSD","BUY",1.0,[_ep("EURUSD",1.0)],10_000)
        self.assertTrue(r.can_trade)

    def test_max_open_trades_blocked(self):
        existing = [_ep(f"SYM{i}",0.5) for i in range(5)]
        r = self.eng.check("NEWSYM","BUY",0.5,existing,10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_OPEN_TRADES", r.reason)

    def test_max_open_trades_four_allowed(self):
        existing = [_ep(f"SYM{i}",0.5) for i in range(4)]
        r = self.eng.check("NEWSYM","BUY",0.5,existing,10_000)
        self.assertTrue(r.can_trade)

    def test_projected_total_risk_correct(self):
        existing = [_ep("EURUSD",1.0),_ep("GBPUSD",1.0)]
        r = self.eng.check("USDJPY","BUY",1.5,existing,10_000)
        self.assertAlmostEqual(r.projected_total_risk, 3.5, places=5)

    def test_empty_positions_allowed(self):
        r = self.eng.check("EURUSD","BUY",1.0,[],10_000)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "EXPOSURE_OK")

    def test_none_positions_treated_as_empty(self):
        r = self.eng.check("EURUSD","BUY",1.0,None,10_000)
        self.assertTrue(r.can_trade)

    def test_fail_closed_on_exception(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, '_check_inner', side_effect=AttributeError("corrupt")):
            r = eng.check("EURUSD","BUY",1.0,[],10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_on_exception(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, '_check_inner', side_effect=AttributeError("corrupt")):
            r = eng.check("EURUSD","BUY",1.0,[],10_000)
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_get_snapshot_fail_closed_reraises(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(eng, '_snapshot_inner', side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                eng.get_snapshot([])

    def test_get_snapshot_fail_open_returns_empty(self):
        eng = ExposureControlEngine(config=self.cfg, fail_mode=FailMode.FAIL_OPEN)
        with patch.object(eng, '_snapshot_inner', side_effect=RuntimeError("boom")):
            snap = eng.get_snapshot([])
        self.assertIsNotNone(snap)
        self.assertEqual(snap.total_risk_percent, 0.0)

    def test_result_snapshot_populated(self):
        r = self.eng.check("EURUSD","BUY",1.0,[],10_000)
        self.assertIsNotNone(r.snapshot)


# ============================================================
# TOPIC 7 - Fail-Closed Behaviour (22 tests)
# ============================================================
class TestFailClosedBehaviour(unittest.TestCase):
    """
    ISSUE before FIX #6:
      CorrelationFilter: except: allow_trade=True  <- SILENT no log!
      ExposureControl:   no try/except
      VolatilityFilter:  no try/except
      PortfolioRisk:     no try/except

    PATCH: fail_mode.py SSoT; _fail_mode cached in __init__;
           try/except in all check() methods; default FAIL_CLOSED.
    BACKWARD COMPAT: All check() signatures unchanged.
    """

    def test_failmode_is_str_enum(self):
        self.assertEqual(FailMode.FAIL_CLOSED, "FAIL_CLOSED")
        self.assertEqual(FailMode.FAIL_OPEN,   "FAIL_OPEN")

    def test_coerce_lowercase(self):
        self.assertIs(coerce_fm("fail_closed"), FailMode.FAIL_CLOSED)

    def test_coerce_mixed_case(self):
        self.assertIs(coerce_fm("Fail_Open"), FailMode.FAIL_OPEN)

    def test_coerce_passthrough(self):
        self.assertIs(coerce_fm(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)

    def test_ssot_vf(self):
        self.assertIs(_vf_mod.FailMode, _fm_mod.FailMode)

    def test_ssot_cf(self):
        self.assertIs(_cf_mod.FailMode, _fm_mod.FailMode)

    def test_ssot_ec(self):
        self.assertIs(_ec_mod.FailMode, _fm_mod.FailMode)

    def test_ssot_pr(self):
        self.assertIs(_pr_mod.FailMode, _fm_mod.FailMode)

    def test_default_vf(self):
        self.assertIs(VolatilityFilter()._fail_mode,     FailMode.FAIL_CLOSED)

    def test_default_ec(self):
        self.assertIs(ExposureControlEngine()._fail_mode, FailMode.FAIL_CLOSED)

    def test_default_cf(self):
        self.assertIs(CorrelationFilter()._fail_mode,    FailMode.FAIL_CLOSED)

    def test_default_pr(self):
        self.assertIs(PortfolioRiskManager()._fail_mode, FailMode.FAIL_CLOSED)

    def test_vf_fail_open_kwarg(self):
        self.assertIs(
            VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN))._fail_mode,
            FailMode.FAIL_OPEN)

    def test_ec_fail_open_kwarg(self):
        self.assertIs(ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)._fail_mode,
                      FailMode.FAIL_OPEN)

    def test_cf_fail_open_kwarg(self):
        self.assertIs(CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)._fail_mode,
                      FailMode.FAIL_OPEN)

    def test_pr_fail_open_kwarg(self):
        self.assertIs(PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)._fail_mode,
                      FailMode.FAIL_OPEN)

    def test_vf_exception_logged_fail_closed(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_CLOSED, min_atr_bars=5))
        with patch.object(vf, '_check_inner', side_effect=ZeroDivisionError("zero")):
            with self.assertLogs("risk.volatility_filter", level="ERROR"):
                r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_vf_exception_logged_fail_open(self):
        vf = VolatilityFilter(VolatilityConfig(fail_mode=FailMode.FAIL_OPEN, min_atr_bars=5))
        with patch.object(vf, '_check_inner', side_effect=ZeroDivisionError("zero")):
            with self.assertLogs("risk.volatility_filter", level="CRITICAL"):
                r = vf.check(0.001, [0.001]*10, 0.0002, 0.0002, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_ec_exception_logged_fail_closed(self):
        ec = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(ec, '_check_inner', side_effect=RuntimeError("corrupt")):
            with self.assertLogs("risk.exposure_control", level="ERROR"):
                r = ec.check("EURUSD","BUY",1.0,[],10_000)
        self.assertFalse(r.can_trade)

    def test_cf_exception_logged_fail_closed(self):
        cf = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("down")):
            with self.assertLogs("risk.correlation_filter", level="CRITICAL"):
                r = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertFalse(r.can_trade)

    def test_pr_fail_closed_on_exception(self):
        pr = PortfolioRiskManager(fail_mode=FailMode.FAIL_CLOSED)
        t  = _otr("EURUSD","BUY",100,1.10,1.09)
        with patch.object(pr, '_check_inner', side_effect=RuntimeError("calc")):
            r = pr.check(t, [])
        self.assertFalse(r.can_trade)

    def test_pr_fail_open_on_exception(self):
        pr = PortfolioRiskManager(fail_mode=FailMode.FAIL_OPEN)
        t  = _otr("EURUSD","BUY",100,1.10,1.09)
        with patch.object(pr, '_check_inner', side_effect=RuntimeError("calc")):
            r = pr.check(t, [])
        self.assertTrue(r.can_trade)


# ============================================================
# TOPIC 8 - Portfolio Correlation Calculations (15 tests)
# ============================================================
class TestPortfolioCorrelationCalcs(unittest.TestCase):
    """
    ISSUE before FIX #6: CorrelationFilter.check() no outer try/except.
    Per-pair crash -> corr=0.0 (inner catch OK).
    Outer crash -> propagate -> fail_mode gate bypass.

    PRODUCTION: abs(corr) >= max_corr (inclusive), same-symbol skipped.
    BACKWARD COMPAT: check(symbol, direction, open_positions) unchanged.
    """

    def _cf(self, max_corr=0.85, fail_mode=FailMode.FAIL_CLOSED, engine=None):
        cfg = CorrelationFilterConfig(max_corr=max_corr, min_bars=0)
        return CorrelationFilter(config=cfg, correlation_engine=engine,
                                 fail_mode=fail_mode)

    def test_high_positive_corr_blocked(self):
        cf = self._cf(engine=_mock_engine({("EURUSD","GBPUSD"):0.92}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("CORR_TOO_HIGH", r.reason)

    def test_high_negative_corr_blocked(self):
        cf = self._cf(engine=_mock_engine({("EURUSD","USDCHF"):-0.92}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"USDCHF"}]))
        self.assertFalse(r.can_trade)

    def test_low_corr_allowed(self):
        cf = self._cf(engine=_mock_engine({("EURUSD","USDJPY"):0.30}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"USDJPY"}]))
        self.assertTrue(r.can_trade)
        self.assertEqual(r.reason, "CORR_OK")

    def test_boundary_at_threshold_blocked(self):
        """corr=0.85 >= 0.85 -> blocked (inclusive >=)."""
        cf = self._cf(engine=_mock_engine({("EURUSD","GBPUSD"):0.85}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertFalse(r.can_trade)

    def test_just_below_threshold_allowed(self):
        cf = self._cf(engine=_mock_engine({("EURUSD","GBPUSD"):0.849}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_same_symbol_skipped(self):
        engine = MagicMock()
        engine.get_correlation = AsyncMock(side_effect=AssertionError("must not call"))
        cf = self._cf(engine=engine)
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"EURUSD"}]))
        self.assertTrue(r.can_trade)

    def test_per_pair_engine_crash_gives_zero(self):
        engine = MagicMock()
        engine.get_correlation = AsyncMock(side_effect=ConnectionError("down"))
        cf = self._cf(engine=engine)
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_no_positions_allowed(self):
        r = asyncio.run(self._cf().check("EURUSD","BUY",[]))
        self.assertTrue(r.can_trade)
        self.assertIn("NO_POSITIONS_OR_ENGINE", r.reason)

    def test_no_engine_allowed(self):
        r = asyncio.run(CorrelationFilter().check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertTrue(r.can_trade)

    def test_early_exit_on_first_breach(self):
        calls = []
        async def _get(s1, s2):
            calls.append((s1,s2))
            return 0.92 if s2=="GBPUSD" else 0.20
        engine = MagicMock()
        engine.get_correlation = AsyncMock(side_effect=_get)
        cf  = self._cf(engine=engine)
        asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"},{"symbol":"AUDUSD"}]))
        self.assertEqual(len(calls), 1)

    def test_pair_checked_field_populated(self):
        cf = self._cf(engine=_mock_engine({("EURUSD","GBPUSD"):0.92}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertEqual(r.pair_checked, "GBPUSD")

    def test_correlation_value_in_result(self):
        cf = self._cf(engine=_mock_engine({("EURUSD","GBPUSD"):0.92}))
        r  = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertAlmostEqual(r.correlation, 0.92, places=3)

    def test_outer_exception_fail_closed_blocks(self):
        cf = self._cf(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("outer")):
            r = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_outer_exception_fail_open_allows(self):
        cf = self._cf(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("outer")):
            r = asyncio.run(cf.check("EURUSD","BUY",[{"symbol":"GBPUSD"}]))
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_multiple_low_corr_allowed(self):
        engine = _mock_engine({
            ("EURUSD","USDJPY"):0.10, ("EURUSD","AUDUSD"):0.25,
            ("EURUSD","NZDUSD"):0.35,
        })
        pos = [{"symbol":"USDJPY"},{"symbol":"AUDUSD"},{"symbol":"NZDUSD"}]
        r   = asyncio.run(self._cf(engine=engine).check("EURUSD","BUY",pos))
        self.assertTrue(r.can_trade)


# ============================================================
# Integration (5 tests)
# ============================================================
class TestIntegration(unittest.TestCase):
    """Cross-gate regression guards for FIX #4-#7 chain."""

    def test_xauusd_pip_consistent(self):
        self.assertEqual(_ls_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)
        self.assertEqual(_pr_mod._PIP_VALUE_TABLE["XAUUSD"], 1.0)

    def test_otr_and_lot_sizer_agree(self):
        r   = asyncio.run(_sizer().calculate("XAUUSD", 10_000, 50))
        lot = r.lot_size
        t   = _otr("XAUUSD","BUY",lot,2050,2000,10_000)
        self.assertAlmostEqual(t.risk_percent, r.risk_percent, delta=0.1)

    def test_all_modules_parse_clean(self):
        import ast
        for stem in ('fail_mode','volatility_filter','portfolio_risk',
                     'correlation_filter','exposure_control','lot_sizing'):
            src = open(os.path.join(_HERE, f'{stem}.py')).read()
            try:
                ast.parse(src)
            except SyntaxError as e:
                self.fail(f"SyntaxError in {stem}.py: {e}")

    def test_fail_mode_single_object(self):
        for mod in (_vf_mod, _cf_mod, _ec_mod, _pr_mod):
            self.assertIs(mod.FailMode, _fm_mod.FailMode,
                          f"{mod.__name__}.FailMode is not fail_mode.FailMode")

    def test_exposure_blocks_xauusd_oversize(self):
        eng = ExposureControlEngine(
            config=ExposureConfig(max_risk_per_symbol=2.0))
        r = eng.check("XAUUSD","BUY",1.5,[_ep("XAUUSD",1.5)],10_000)
        self.assertFalse(r.can_trade)
        self.assertIn("MAX_SYMBOL_RISK", r.reason)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in (
        TestNewsEventBlocking, TestATRSpikeRobustness,
        TestSymbolSpecificThresholds, TestGoldPipValue,
        TestCryptoPipValue, TestExposureCalculation,
        TestFailClosedBehaviour, TestPortfolioCorrelationCalcs,
        TestIntegration,
    ):
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
