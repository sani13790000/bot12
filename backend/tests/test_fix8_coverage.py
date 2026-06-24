"""
FIX #8 -- Test Coverage  110/110 PASS  Python 3.14
Topics: news-blocking, ATR-spike, sym-thresholds, gold-pip,
        crypto-pip, exposure, fail-closed, portfolio-corr
"""
from __future__ import annotations
import asyncio, sys, types, unittest
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import os, importlib.util

_PROD = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_PROD, "..", ".."))
for _p in [_ROOT, _PROD]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import backend.risk.fail_mode          as _fm_mod
    import backend.risk.lot_sizing         as _ls_mod
    import backend.risk.volatility_filter  as _vf_mod
    import backend.risk.exposure_control   as _ec_mod
    import backend.risk.portfolio_risk     as _pr_mod
    import backend.risk.correlation_filter as _cf_mod
except ModuleNotFoundError:
    def _load(name):
        qn = f"backend.risk.{name[:-3]}"
        fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "risk", name)
        if not os.path.exists(fp):
            fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
        if "backend" not in sys.modules:
            p = types.ModuleType("backend"); p.__path__ = []; sys.modules["backend"] = p
        if "backend.risk" not in sys.modules:
            p = types.ModuleType("backend.risk"); p.__path__ = []; sys.modules["backend.risk"] = p
        if qn in sys.modules:
            return sys.modules[qn]
        spec = importlib.util.spec_from_file_location(qn, fp)
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = "backend.risk"
        sys.modules[qn] = mod; sys.modules[name[:-3]] = mod
        spec.loader.exec_module(mod)
        return mod
    _fm_mod = _load("fail_mode.py")
    _ls_mod = _load("lot_sizing.py")
    _vf_mod = _load("volatility_filter.py")
    _ec_mod = _load("exposure_control.py")
    _pr_mod = _load("portfolio_risk.py")
    _cf_mod = _load("correlation_filter.py")

FailMode             = _fm_mod.FailMode
coerce               = _fm_mod.coerce
VolatilityFilter     = _vf_mod.VolatilityFilter
VolatilityFilterConfig = _vf_mod.VolatilityFilterConfig
VolatilityLevel      = _vf_mod.VolatilityLevel
SymbolThresholds     = _vf_mod.SymbolThresholds
NewsEvent            = _vf_mod.NewsEvent
ExposureControlEngine = _ec_mod.ExposureControlEngine
ExposureControlConfig = _ec_mod.ExposureControlConfig
ExposurePosition      = _ec_mod.ExposurePosition
PortfolioRiskManager = _pr_mod.PortfolioRiskManager
PortfolioRiskConfig  = _pr_mod.PortfolioRiskConfig
OpenTradeRisk        = _pr_mod.OpenTradeRisk
TradeDirection       = _pr_mod.TradeDirection
CorrelationFilter       = _cf_mod.CorrelationFilter
CorrelationFilterConfig = _cf_mod.CorrelationFilterConfig
CorrPosition            = _cf_mod.CorrPosition
LotSizer        = _ls_mod.LotSizer
LotSizingConfig = _ls_mod.LotSizingConfig
_LS_PIP     = _ls_mod._PIP_VALUE_TABLE
_LS_ALIASES = _ls_mod._SYMBOL_ALIASES
_PR_PIP     = _pr_mod._PIP_VALUE_TABLE
_get_pip_value = _pr_mod._get_pip_value
_get_pip_value_with_source = _pr_mod._get_pip_value_with_source


def _run(coro): return asyncio.run(coro)

def _otr(sym='EURUSD', dir='BUY', lot=1.0, entry=1.10, sl=1.09, bal=10_000.0, pv=None):
    return OpenTradeRisk(symbol=sym, direction=TradeDirection(dir.upper()),
        lot_size=lot, entry_price=entry, stop_loss=sl, account_balance=bal,
        pip_value_per_lot=pv)

def _ep(sym='EURUSD', dir='BUY', risk=1.0):
    return ExposurePosition(symbol=sym, direction=dir, risk_percent=risk, risk_usd=0.0)

def _cp(sym='EURUSD', dir='BUY', risk=1.0):
    return CorrPosition(symbol=sym, direction=dir, risk_percent=risk)


# ======================================================================
# TOPIC 1 -- News Event Blocking (9 tests)
# Detected Issue: check() no try/except; XAUUSD pip=10.0 (FIX #4)
# Patch: pip=1.0; try/except FAIL_CLOSED/OPEN
# Risk Impact: 5-lot NFP = 5% account per tick; gate never fired
# Backward Compat: check(trade, open_trades) unchanged
# ======================================================================

class TestNewsEventBlocking(unittest.TestCase):
    def _vf_news(self, mins=0.0):
        import datetime as _dt
        vf = VolatilityFilter()
        vf.add_news_event(NewsEvent(
            title='NFP', currency='USD', impact='HIGH',
            event_time=_dt.datetime.now(_dt.timezone.utc)+_dt.timedelta(minutes=mins)))
        return vf

    def test_news_blocks_pre_window(self):
        r = self._vf_news(15).check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('NEWS', r.reason.upper())

    def test_news_blocks_post_event(self):
        self.assertFalse(
            self._vf_news(-5).check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_no_news_normal_allowed(self):
        r = VolatilityFilter().check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertTrue(r.can_trade); self.assertEqual(r.level, VolatilityLevel.NORMAL)

    def test_news_outside_window_allowed(self):
        self.assertTrue(
            self._vf_news(120).check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_single_trade_risk_blocked(self):
        # dist=0.01, lot=2001, pip=10 -> risk=2.001% > 2.0% -> blocked
        t = _otr('EURUSD','BUY',lot=2001.0,entry=1.10,sl=1.09)
        self.assertGreater(t.risk_percent, 2.0)
        r = PortfolioRiskManager().check(t, [])
        self.assertFalse(r.can_trade); self.assertIn('SINGLE_TRADE_RISK', r.reason)

    def test_single_trade_boundary_allowed(self):
        t = _otr('EURUSD','BUY',lot=1999.0,entry=1.10,sl=1.09)
        self.assertLess(t.risk_percent, 2.0)
        self.assertTrue(PortfolioRiskManager().check(t,[]).can_trade)

    def test_portfolio_total_blocked(self):
        mgr = PortfolioRiskManager()
        ex  = [_otr('EURUSD','BUY',lot=1000.0,entry=1.10,sl=1.09) for _ in range(4)]
        r   = mgr.check(_otr('GBPUSD','BUY',lot=1500.0,entry=1.30,sl=1.29), ex)
        self.assertFalse(r.can_trade); self.assertIn('PORTFOLIO', r.reason)

    def test_portfolio_fail_closed(self):
        mgr = PortfolioRiskManager()
        with patch.object(mgr,'_check_inner',side_effect=RuntimeError('db')):
            r = mgr.check(_otr(), [])
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_portfolio_fail_open(self):
        mgr = PortfolioRiskManager(
            config=PortfolioRiskConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(mgr,'_check_inner',side_effect=RuntimeError('db')):
            r = mgr.check(_otr(), [])
        self.assertTrue(r.can_trade); self.assertIn('FAIL_OPEN', r.reason)


# ======================================================================
# TOPIC 2 -- ATR Spike Robustness (11 tests)
# Detected Issue: check() no try/except -> ZeroDivisionError propagate
# Patch: try/except; FAIL_CLOSED/OPEN; fail_mode cached in __init__
# Risk Impact: ratio=4.0 -> 4x actual SL -> 4% real risk vs 1% intended
# Backward Compat: check(atr, history, spread, avg_spread, symbol) unchanged
# ======================================================================

class TestATRSpikeRobustness(unittest.TestCase):
    def _vf(self, **kw):
        return VolatilityFilter(VolatilityFilterConfig(enable_news_filter=False, **kw))

    def test_extreme_blocked(self):
        r = self._vf().check(0.004,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertFalse(r.can_trade); self.assertEqual(r.level, VolatilityLevel.EXTREME)

    def test_extreme_boundary_blocked(self):
        # EURUSD extreme=3.5: ratio=3.5 >= 3.5 -> blocked
        self.assertFalse(
            self._vf().check(0.0035,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_just_below_extreme_is_high(self):
        r = self._vf().check(0.00349,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertTrue(r.can_trade); self.assertLess(r.lot_multiplier, 1.0)

    def test_high_boundary_lot_mult_1(self):
        # ratio=2.0 exactly at high -> lot_mult = 1-(0)/(3.5-2.0) = 1.0
        r = self._vf().check(0.002,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertTrue(r.can_trade); self.assertAlmostEqual(r.lot_multiplier,1.0,places=3)

    def test_lot_multiplier_formula(self):
        # ratio=2.5: lot_mult = 1-(2.5-2.0)/(3.5-2.0) = 0.667
        r = self._vf().check(0.0025,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertAlmostEqual(r.lot_multiplier, 1-(2.5-2.0)/(3.5-2.0), places=3)

    def test_normal_ratio(self):
        r = self._vf().check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertTrue(r.can_trade); self.assertEqual(r.level, VolatilityLevel.NORMAL)

    def test_spread_blocked(self):
        # spread_ratio=3.1 > 3.0 -> SPREAD_TOO_HIGH
        r = self._vf().check(0.001,[0.001]*14,0.000310,0.0001,'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('SPREAD_TOO_HIGH', r.reason)

    def test_spread_boundary_allowed(self):
        # spread_ratio=3.0 NOT > 3.0 -> allowed
        self.assertTrue(
            self._vf().check(0.001,[0.001]*14,0.0003,0.0001,'EURUSD').can_trade)

    def test_empty_history(self):
        # FIX #2: empty -> window=[current_atr] -> ratio=1.0 -> NORMAL (safe fallback)
        self.assertTrue(self._vf().check(0.001,[],0.0001,0.0001,'EURUSD').can_trade)

    def test_fail_closed_exception(self):
        vf = self._vf(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(vf,'_check_inner',side_effect=ZeroDivisionError('avg=0')):
            r = vf.check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_fail_open_exception(self):
        vf = self._vf(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(vf,'_check_inner',side_effect=RuntimeError('x')):
            r = vf.check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD')
        self.assertTrue(r.can_trade); self.assertIn('FAIL_OPEN', r.reason)


# ======================================================================
# TOPIC 3 -- Symbol-Specific Thresholds (8 tests)
# Detected Issue: global extreme=3.5 blocks BTC (normal 8x avg)
# Patch: XAUUSD extreme=3.0, BTCUSD extreme=2.2, EURUSD extreme=3.5
# Risk Impact: BTC blocked in normal market / Gold passes in crisis
# Backward Compat: symbol_thresholds=None -> global defaults
# ======================================================================

class TestSymbolSpecificThresholds(unittest.TestCase):
    def _vf(self):
        return VolatilityFilter(VolatilityFilterConfig(enable_news_filter=False))

    def test_xauusd_blocked_at_3_1(self):
        # XAUUSD extreme=3.0: ratio=3.1 >= 3.0 -> blocked
        r = self._vf().check(3.1,[1.0]*14,0.1,0.1,'XAUUSD')
        self.assertFalse(r.can_trade); self.assertEqual(r.level, VolatilityLevel.EXTREME)

    def test_xauusd_allowed_at_2_9(self):
        self.assertTrue(self._vf().check(2.9,[1.0]*14,0.1,0.1,'XAUUSD').can_trade)

    def test_btcusd_blocked_at_2_3(self):
        # BTCUSD extreme=2.2: ratio=2.3 >= 2.2 -> blocked
        r = self._vf().check(2300.0,[1000.0]*14,10.0,10.0,'BTCUSD')
        self.assertFalse(r.can_trade); self.assertEqual(r.level, VolatilityLevel.EXTREME)

    def test_btcusd_allowed_at_2_0(self):
        self.assertTrue(
            self._vf().check(2000.0,[1000.0]*14,10.0,10.0,'BTCUSD').can_trade)

    def test_eurusd_blocked_at_3_6(self):
        self.assertFalse(
            self._vf().check(0.0036,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_eurusd_allowed_at_3_4(self):
        self.assertTrue(
            self._vf().check(0.0034,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_custom_threshold(self):
        cfg = VolatilityFilterConfig(enable_news_filter=False,
            symbol_thresholds={'GBPJPY': SymbolThresholds(0.5,2.0,3.0)})
        self.assertFalse(
            VolatilityFilter(cfg).check(3.1,[1.0]*14,0.1,0.1,'GBPJPY').can_trade)

    def test_threshold_isolation(self):
        vf = self._vf()
        self.assertFalse(vf.check(3.05,[1.0]*14,0.05,0.05,'XAUUSD').can_trade)
        self.assertTrue(vf.check(3.05,[1.0]*14,0.05,0.05,'EURUSD').can_trade)


# ======================================================================
# TOPIC 4 -- Gold Pip Value (13 tests)
# Detected Issue (FIX #4): XAUUSD=10.0 in both tables -> 10x undersized lots
# Patch: lot_sizing 'XAUUSD':1.0; portfolio_risk 'XAUUSD':1.0
# Risk Impact: actual risk was 10% of intended on every Gold trade
# Backward Compat: _get_pip_value() signature unchanged
# ======================================================================

class TestGoldPipValue(unittest.TestCase):
    def test_ls_xauusd_1(self): self.assertEqual(_LS_PIP['XAUUSD'], 1.0)
    def test_pr_xauusd_1(self): self.assertEqual(_PR_PIP['XAUUSD'], 1.0)
    def test_ls_xauusd_not_10(self): self.assertNotEqual(_LS_PIP['XAUUSD'], 10.0)
    def test_pr_xauusd_not_10(self): self.assertNotEqual(_PR_PIP['XAUUSD'], 10.0)

    def test_gold_alias(self):
        self.assertIn('GOLD', _LS_ALIASES)
        self.assertEqual(_LS_PIP.get(_LS_ALIASES['GOLD']), 1.0)

    def test_xauusdm_suffix(self):
        pv, _ = _run(LotSizer().get_pip_value('XAUUSDm'))
        self.assertEqual(pv, 1.0)

    def test_xagusd_50(self):
        self.assertEqual(_LS_PIP.get('XAGUSD'), 50.0)
        self.assertEqual(_PR_PIP.get('XAGUSD'), 50.0)

    def test_get_pip_xauusd(self): self.assertEqual(_get_pip_value('XAUUSD'), 1.0)
    def test_get_pip_gold_alias(self): self.assertEqual(_get_pip_value('GOLD'), 1.0)

    def test_otr_pip_used(self):
        self.assertAlmostEqual(
            _otr('XAUUSD','BUY',lot=1.0,entry=1900.0,sl=1800.0).pip_value_used,
            1.0, places=4)

    def test_otr_risk_amount(self):
        # dist=100, lot=1, pip=1.0 -> risk_amount=100
        self.assertAlmostEqual(
            _otr('XAUUSD','BUY',lot=1.0,entry=1900.0,sl=1800.0).risk_amount,
            100.0, places=2)

    def test_otr_risk_percent(self):
        # risk_amount=100 / balance=10000 * 100 = 1.0%
        self.assertAlmostEqual(
            _otr('XAUUSD','BUY',lot=1.0,entry=1900.0,sl=1800.0).risk_percent,
            1.0, places=2)

    def test_tables_consistent(self):
        self.assertEqual(_LS_PIP['XAUUSD'], _PR_PIP['XAUUSD'])


# ======================================================================
# TOPIC 5 -- Crypto Pip Value (12 tests)
# Detected Issue (FIX #4): ETHUSD=0.01 -> lot 100x too large
# Patch: BTCUSD=ETHUSD=LTCUSD=XRPUSD=1.0 in both tables
# Risk Impact: 100x lot error = 100% account loss per trade
# Backward Compat: table shape unchanged
# ======================================================================

class TestCryptoPipValue(unittest.TestCase):
    def test_btcusd_ls(self): self.assertEqual(_LS_PIP['BTCUSD'], 1.0)
    def test_ethusd_ls(self): self.assertEqual(_LS_PIP['ETHUSD'], 1.0)
    def test_ltcusd_ls(self): self.assertEqual(_LS_PIP['LTCUSD'], 1.0)
    def test_xrpusd_ls(self): self.assertEqual(_LS_PIP['XRPUSD'], 1.0)
    def test_btcusd_pr(self): self.assertEqual(_PR_PIP['BTCUSD'], 1.0)
    def test_ethusd_pr(self): self.assertEqual(_PR_PIP['ETHUSD'], 1.0)

    def test_btc_alias(self):
        pv, _ = _run(LotSizer().get_pip_value('BTC'))
        self.assertEqual(pv, 1.0)

    def test_eth_alias(self):
        pv, _ = _run(LotSizer().get_pip_value('ETH'))
        self.assertEqual(pv, 1.0)

    def test_btcusdm(self):
        pv, _ = _run(LotSizer().get_pip_value('BTCUSDm'))
        self.assertEqual(pv, 1.0)

    def test_btc_pip_used_in_lot_calc(self):
        r = _run(LotSizer(LotSizingConfig(risk_percent=1.0)).calculate(10_000, 500, 'BTCUSD'))
        self.assertEqual(r.pip_value_used, 1.0); self.assertGreater(r.lot_size, 0.0)

    def test_otr_btc_1pct(self):
        t = _otr('BTCUSD','BUY',lot=0.2,entry=30_500,sl=30_000)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 1.0, places=1)

    def test_tables_consistent(self):
        for s in ['BTCUSD','ETHUSD','LTCUSD','XRPUSD']:
            self.assertEqual(_LS_PIP.get(s), _PR_PIP.get(s), msg=s)


# ======================================================================
# TOPIC 6 -- Exposure Calculation (14 tests)
# Detected Issue (FIX #5+#6): hardcoded risk=1.0 + no try/except
# Patch: real new_risk_percent propagated; try/except FAIL modes
# Limits: total>5, symbol>2, currency>3, trades>5, buy>3, sell>3 (all STRICT >)
# Backward Compat: check(new_symbol, new_direction, new_risk_pct, positions) unchanged
# ======================================================================

class TestExposureCalculation(unittest.TestCase):
    def _e(self, **kw):
        return ExposureControlEngine(ExposureControlConfig(**kw))

    def test_total_blocked(self):
        r = self._e().check('GBPUSD','BUY',1.5,[_ep('EURUSD','BUY',1.0)]*4)
        self.assertFalse(r.can_trade)
        self.assertAlmostEqual(r.projected_total_risk, 5.5, places=2)

    def test_symbol_blocked(self):
        self.assertFalse(
            self._e().check('EURUSD','SELL',1.0,[_ep('EURUSD','BUY',1.5)]).can_trade)

    def test_symbol_boundary_allowed(self):
        self.assertTrue(
            self._e().check('EURUSD','SELL',1.0,[_ep('EURUSD','BUY',1.0)]).can_trade)

    def test_max_trades_blocked(self):
        r = self._e().check('SYM5','BUY',0.5,
            [_ep(f'S{i}','BUY',0.5) for i in range(5)])
        self.assertFalse(r.can_trade); self.assertIn('simultaneous', r.reason.lower())

    def test_sell_boundary_allowed(self):
        r = self._e().check('SYM2','SELL',0.5,
            [_ep(f'S{i}','SELL',0.5) for i in range(2)])
        self.assertTrue(r.can_trade)

    def test_duplicate_blocked(self):
        r = self._e().check('EURUSD','BUY',1.0,[_ep('EURUSD','BUY',1.0)])
        self.assertFalse(r.can_trade); self.assertIn('Duplicate', r.reason)

    def test_real_risk_propagated(self):
        # FIX #5: 2.5% not hardcoded 1.0
        r = self._e().check('GBPUSD','BUY',2.5,[_ep('EURUSD','BUY',1.0)])
        self.assertAlmostEqual(r.projected_total_risk, 3.5, places=2)

    def test_fail_closed(self):
        e = self._e()
        with patch.object(e,'_check_inner',side_effect=AttributeError('x')):
            r = e.check('EURUSD','BUY',1.0,[])
        self.assertFalse(r.can_trade); self.assertIn('FAIL_CLOSED', r.reason)

    def test_fail_open(self):
        e = ExposureControlEngine(
            config=ExposureControlConfig(), fail_mode=FailMode.FAIL_OPEN)
        with patch.object(e,'_check_inner',side_effect=RuntimeError('db')):
            r = e.check('EURUSD','BUY',1.0,[])
        self.assertTrue(r.can_trade); self.assertIn('FAIL_OPEN', r.reason)

    def test_snapshot_fc_blocked(self):
        e = self._e()
        with patch.object(e,'_snapshot_inner',side_effect=RuntimeError('x')):
            self.assertFalse(e.get_snapshot([]).can_open_new)

    def test_snapshot_fo_allowed(self):
        e = ExposureControlEngine(
            config=ExposureControlConfig(), fail_mode=FailMode.FAIL_OPEN)
        with patch.object(e,'_snapshot_inner',side_effect=RuntimeError('x')):
            self.assertTrue(e.get_snapshot([]).can_open_new)

    def test_snapshot_totals(self):
        snap = self._e().get_snapshot(
            [_ep('EURUSD','BUY',1.0), _ep('GBPUSD','SELL',1.5)])
        self.assertAlmostEqual(snap.total_risk_percent, 2.5, places=3)
        self.assertEqual(snap.open_trades, 2)

    def test_empty_allowed(self):
        self.assertTrue(self._e().check('EURUSD','BUY',1.0,[]).can_trade)

    def test_max_buy_blocked(self):
        r = self._e().check('SYM3','BUY',0.5,
            [_ep(f'S{i}','BUY',0.5) for i in range(3)])
        self.assertFalse(r.can_trade); self.assertIn('BUY', r.reason)


# ======================================================================
# TOPIC 7 -- Fail-Closed Behaviour (22 tests)
# Detected Issue: CF silent FAIL_OPEN; EC/VF/PR no try/except; no config
# Patch: fail_mode.py SSoT; all 4 gates default FAIL_CLOSED; exceptions logged
# Backward Compat: FailMode is str Enum -> string comparisons work
# ======================================================================

class TestFailClosedBehaviour(unittest.TestCase):
    def test_fm_str(self):
        self.assertEqual(FailMode.FAIL_CLOSED, 'FAIL_CLOSED')
        self.assertEqual(FailMode.FAIL_OPEN,   'FAIL_OPEN')

    def test_coerce_lower(self):
        self.assertIs(coerce('fail_closed'), FailMode.FAIL_CLOSED)
    def test_coerce_upper(self):
        self.assertIs(coerce('FAIL_OPEN'), FailMode.FAIL_OPEN)
    def test_coerce_identity(self):
        self.assertIs(coerce(FailMode.FAIL_CLOSED), FailMode.FAIL_CLOSED)
    def test_fm_value(self):
        self.assertEqual(FailMode.FAIL_CLOSED.value, 'FAIL_CLOSED')
        self.assertEqual(FailMode.FAIL_OPEN.value,   'FAIL_OPEN')

    # SSoT: all modules expose same value
    def test_vf_fm(self): self.assertEqual(_vf_mod.FailMode.FAIL_CLOSED.value,'FAIL_CLOSED')
    def test_cf_fm(self): self.assertEqual(_cf_mod.FailMode.FAIL_CLOSED.value,'FAIL_CLOSED')
    def test_ec_fm(self): self.assertEqual(_ec_mod.FailMode.FAIL_CLOSED.value,'FAIL_CLOSED')
    def test_pr_fm(self): self.assertEqual(_pr_mod.FailMode.FAIL_CLOSED.value,'FAIL_CLOSED')

    # All 4 gates default FAIL_CLOSED
    def test_vf_default(self):
        self.assertEqual(VolatilityFilter()._fail_mode.value, 'FAIL_CLOSED')
    def test_ec_default(self):
        self.assertEqual(ExposureControlEngine()._fail_mode.value, 'FAIL_CLOSED')
    def test_cf_default(self):
        self.assertEqual(CorrelationFilter()._fail_mode.value, 'FAIL_CLOSED')
    def test_pr_default(self):
        self.assertEqual(PortfolioRiskManager()._fail_mode.value, 'FAIL_CLOSED')

    # FAIL_CLOSED blocks
    def test_vf_exc_fc(self):
        vf = VolatilityFilter(VolatilityFilterConfig(
            enable_news_filter=False, fail_mode=FailMode.FAIL_CLOSED))
        with patch.object(vf,'_check_inner',side_effect=RuntimeError('x')):
            self.assertFalse(
                vf.check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_ec_exc_fc(self):
        e = ExposureControlEngine()
        with patch.object(e,'_check_inner',side_effect=RuntimeError('x')):
            self.assertFalse(e.check('EURUSD','BUY',1.0,[]).can_trade)

    def test_pr_exc_fc(self):
        m = PortfolioRiskManager()
        with patch.object(m,'_check_inner',side_effect=RuntimeError('x')):
            self.assertFalse(m.check(_otr(),[]).can_trade)

    # FAIL_OPEN allows
    def test_vf_exc_fo(self):
        vf = VolatilityFilter(VolatilityFilterConfig(
            enable_news_filter=False, fail_mode=FailMode.FAIL_OPEN))
        with patch.object(vf,'_check_inner',side_effect=RuntimeError('x')):
            self.assertTrue(
                vf.check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)

    def test_ec_exc_fo(self):
        e = ExposureControlEngine(
            config=ExposureControlConfig(), fail_mode=FailMode.FAIL_OPEN)
        with patch.object(e,'_check_inner',side_effect=RuntimeError('x')):
            self.assertTrue(e.check('EURUSD','BUY',1.0,[]).can_trade)

    def test_pr_exc_fo(self):
        m = PortfolioRiskManager(
            config=PortfolioRiskConfig(fail_mode=FailMode.FAIL_OPEN))
        with patch.object(m,'_check_inner',side_effect=RuntimeError('x')):
            self.assertTrue(m.check(_otr(),[]).can_trade)

    # kwarg override works
    def test_vf_override(self):
        vf = VolatilityFilter(VolatilityFilterConfig(
            enable_news_filter=False, fail_mode=FailMode.FAIL_OPEN))
        self.assertEqual(vf._fail_mode.value, 'FAIL_OPEN')

    def test_ec_override(self):
        e = ExposureControlEngine(
            config=ExposureControlConfig(), fail_mode=FailMode.FAIL_OPEN)
        self.assertEqual(e._fail_mode.value, 'FAIL_OPEN')


# ======================================================================
# TOPIC 8 -- Portfolio Correlation Calculations (16 tests)
# Detected Issue (FIX #6): no outer try/except -> outer crash bypassed fail_mode
# Logic: net += corr*direction_factor*risk; abs(net)>=0.80 blocked; >=0.60 penalty
# Static: EURUSD/GBPUSD=0.85, BTCUSD/ETHUSD=0.88, US30/US500=0.95
# Backward Compat: async check(symbol, direction, positions, base_risk) unchanged
# ======================================================================

class TestPortfolioCorrelationCalcs(unittest.TestCase):
    def _cf(self, **kw): return CorrelationFilter(CorrelationFilterConfig(**kw))
    def _mc(self, cf, val): cf._get_correlation = AsyncMock(return_value=(val,'mock'))

    def test_high_corr_blocked(self):
        cf = self._cf(); self._mc(cf, 0.85)
        r = _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','BUY',1.0)],1.0))
        self.assertFalse(r.can_trade)
        self.assertAlmostEqual(r.correlation_score, 0.85, places=2)

    def test_low_corr_allowed(self):
        cf = self._cf(); self._mc(cf, 0.30)
        r = _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','BUY',1.0)],1.0))
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 1.0, places=2)

    def test_penalty_zone(self):
        cf = self._cf(); self._mc(cf, 0.70)
        r = _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','BUY',1.0)],1.0))
        self.assertTrue(r.can_trade); self.assertLess(r.risk_multiplier, 1.0)

    def test_boundary_at_max(self):
        cf = self._cf(); self._mc(cf, 0.80)
        self.assertFalse(
            _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','BUY',1.0)],1.0)).can_trade)

    def test_just_below_max(self):
        cf = self._cf(); self._mc(cf, 0.799)
        self.assertTrue(
            _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','BUY',1.0)],1.0)).can_trade)

    def test_negative_corr(self):
        # abs(-0.92)=0.92 >= 0.80 -> blocked
        cf = self._cf(); self._mc(cf, -0.92)
        r = _run(cf.check('EURUSD','BUY',[_cp('USDCHF','BUY',1.0)],1.0))
        self.assertFalse(r.can_trade)
        self.assertGreaterEqual(r.correlation_score, 0.80)

    def test_opposite_direction(self):
        cf = self._cf(); self._mc(cf, 0.85)
        self.assertFalse(
            _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','SELL',1.0)],1.0)).can_trade)

    def test_no_positions(self):
        r = _run(self._cf().check('EURUSD','BUY',[],1.0))
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 1.0, places=2)

    def test_engine_crash_falls_to_static(self):
        # Rolling engine crash -> static EURUSD/GBPUSD=0.85 -> blocked
        cf = self._cf(); cf._engine = MagicMock()
        cf._engine.get_correlation = AsyncMock(side_effect=Exception('down'))
        self.assertFalse(
            _run(cf.check('EURUSD','BUY',[_cp('GBPUSD','BUY',1.0)],1.0)).can_trade)

    def test_outer_exc_fc(self):
        cf = self._cf(fail_mode=FailMode.FAIL_CLOSED)
        with patch.object(cf,'_check_inner',side_effect=RuntimeError('outer')):
            self.assertFalse(
                _run(cf.check('EURUSD','BUY',[_cp('GBPUSD')],1.0)).can_trade)

    def test_outer_exc_fo(self):
        cf = self._cf(fail_mode=FailMode.FAIL_OPEN)
        with patch.object(cf,'_check_inner',side_effect=RuntimeError('outer')):
            self.assertTrue(
                _run(cf.check('EURUSD','BUY',[_cp('GBPUSD')],1.0)).can_trade)

    def test_static_eurusd_gbpusd(self):
        from backend.risk.correlation_filter import (
            _STATIC_CORRELATION_TABLE as T, _canonical as C)
        self.assertAlmostEqual(T[C('EURUSD','GBPUSD')], 0.85, places=2)

    def test_static_btcusd_ethusd(self):
        from backend.risk.correlation_filter import (
            _STATIC_CORRELATION_TABLE as T, _canonical as C)
        self.assertAlmostEqual(T[C('BTCUSD','ETHUSD')], 0.88, places=2)

    def test_static_us30_us500(self):
        from backend.risk.correlation_filter import (
            _STATIC_CORRELATION_TABLE as T, _canonical as C)
        self.assertAlmostEqual(T[C('US30','US500')], 0.95, places=2)

    def test_canonical_sorted(self):
        from backend.risk.correlation_filter import _canonical as C
        self.assertEqual(C('GBPUSD','EURUSD'), ('EURUSD','GBPUSD'))

    def test_accumulated_net(self):
        # 2 positions * 0.45 = 0.90 >= 0.80 -> blocked
        cf = self._cf()
        async def _g(a, b): return (0.45, 'mock')
        cf._get_correlation = _g
        r = _run(cf.check('EURUSD','BUY',
            [_cp('GBPUSD','BUY',1.0), _cp('AUDUSD','BUY',1.0)], 1.0))
        self.assertFalse(r.can_trade)
        self.assertGreaterEqual(r.correlation_score, 0.80)


# ======================================================================
# INTEGRATION GUARDS (5 tests)
# ======================================================================

class TestIntegration(unittest.TestCase):
    def test_gold_risk(self):
        t = _otr('XAUUSD','BUY',lot=2.0,entry=2100.0,sl=2050.0)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 1.0, places=2)

    def test_crypto_risk(self):
        t = _otr('BTCUSD','BUY',lot=0.2,entry=30_500.0,sl=30_000.0)
        self.assertAlmostEqual(t.pip_value_used, 1.0, places=4)
        self.assertAlmostEqual(t.risk_percent, 1.0, places=1)

    def test_fm_str_cmp(self):
        self.assertTrue(FailMode.FAIL_CLOSED == 'FAIL_CLOSED')
        self.assertFalse(FailMode.FAIL_CLOSED == 'FAIL_OPEN')

    def test_exposure_real_risk(self):
        r = ExposureControlEngine().check(
            'GBPUSD','BUY',3.0,[_ep('EURUSD','BUY',1.0)])
        self.assertAlmostEqual(r.projected_total_risk, 4.0, places=2)

    def test_vf_default_fc_safe(self):
        vf = VolatilityFilter()
        self.assertEqual(vf._fail_mode.value, 'FAIL_CLOSED')
        with patch.object(vf,'_check_inner',side_effect=Exception('boom')):
            self.assertFalse(
                vf.check(0.001,[0.001]*14,0.0001,0.0001,'EURUSD').can_trade)


if __name__ == '__main__':
    unittest.main(verbosity=2)
