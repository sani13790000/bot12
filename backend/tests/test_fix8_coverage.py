"""
backend/tests/test_fix8_coverage.py
FIX #8 - Test Coverage for 8 modified risk modules.

Run:
    cd backend && python -m pytest tests/test_fix8_coverage.py -v
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("OTEL_SDK_DISABLED", "true")

_PROD = Path(__file__).parent.parent / "risk"
_MODULE_CACHE: dict = {}


def _load(name: str) -> types.ModuleType:
    if name in _MODULE_CACHE:
        return _MODULE_CACHE[name]
    full = f"backend.risk.{name}"
    path = _PROD / f"{name}.py"
    source = path.read_text(encoding="utf-8")
    mod = types.ModuleType(full)
    mod.__file__ = str(path)
    mod.__package__ = "backend.risk"
    mod.__spec__ = importlib.util.spec_from_file_location(full, path)
    sys.modules[full] = mod
    exec(compile(source, str(path), "exec"), mod.__dict__)
    _MODULE_CACHE[name] = mod
    return mod


_fm = _load("fail_mode")
_ls = _load("lot_sizing")
_vf = _load("volatility_filter")
_pr = _load("portfolio_risk")
_ec = _load("exposure_control")
_cf = _load("correlation_filter")


def _run(coro):
    return asyncio.run(coro)


def _make_trade(symbol="EURUSD", direction="BUY", lot_size=1.0,
               entry_price=1.10000, stop_loss=1.09000,
               account_balance=10_000.0, pip_value_per_lot=None):
    TD = _pr.TradeDirection
    return _pr.OpenTradeRisk(
        symbol=symbol,
        direction=TD.BUY if direction.upper() == "BUY" else TD.SELL,
        lot_size=lot_size, entry_price=entry_price,
        stop_loss=stop_loss, account_balance=account_balance,
        pip_value_per_lot=pip_value_per_lot,
    )


def _make_ep(symbol="EURUSD", direction="BUY", risk_percent=1.0):
    return _ec.ExposurePosition(symbol=symbol, direction=direction, risk_percent=risk_percent)


def _make_cp(symbol="EURUSD", direction="BUY", risk_percent=1.0):
    return _cf.CorrPosition(symbol=symbol, direction=direction, risk_percent=risk_percent)


# ============================================================
# 1. NEWS EVENT BLOCKING
# ============================================================
class TestNewsEventBlocking(unittest.TestCase):
    """
    Issue: Before FIX #1, _check_news() did not exist.
    Patch: VolatilityFilter._check_news(now) blocks within [before, after] window.
    Risk: 5-lot EURUSD on NFP = 3-8% slippage in <1 second.
    Compat: check() signature unchanged; NewsEvent is additive.
    """

    def _vf(self, event_time, before=30, after=15):
        cfg = _vf.VolatilityFilterConfig(
            enable_news_filter=True,
            news_block_minutes_before=before,
            news_block_minutes_after=after)
        filt = _vf.VolatilityFilter(config=cfg)
        filt.add_news_event(_vf.NewsEvent(
            title="NFP", currency="USD", impact="HIGH", event_time=event_time))
        return filt

    def _call(self, filt):
        return filt.check(0.0001, [0.0001]*20, 0.00010, 0.00010, "EURUSD")

    def test_blocked_15min_before(self):
        et = datetime.now(timezone.utc) + timedelta(minutes=15)
        r = self._call(self._vf(et))
        self.assertFalse(r.can_trade)
        self.assertIn("NEWS_EVENT_BLOCK", r.reason)

    def test_blocked_1min_before(self):
        et = datetime.now(timezone.utc) + timedelta(minutes=1)
        self.assertFalse(self._call(self._vf(et)).can_trade)

    def test_blocked_during_event(self):
        et = datetime.now(timezone.utc)
        self.assertFalse(self._call(self._vf(et)).can_trade)

    def test_blocked_5min_after(self):
        et = datetime.now(timezone.utc) - timedelta(minutes=5)
        self.assertFalse(self._call(self._vf(et)).can_trade)

    def test_allowed_35min_before(self):
        """35 min before > before=30 -> allowed."""
        et = datetime.now(timezone.utc) + timedelta(minutes=35)
        self.assertTrue(self._call(self._vf(et)).can_trade)

    def test_allowed_20min_after(self):
        """20 min after > after=15 -> allowed."""
        et = datetime.now(timezone.utc) - timedelta(minutes=20)
        self.assertTrue(self._call(self._vf(et)).can_trade)

    def test_disabled_filter(self):
        """enable_news_filter=False -> no blocking."""
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=False)
        filt = _vf.VolatilityFilter(config=cfg)
        et = datetime.now(timezone.utc) + timedelta(minutes=5)
        filt.add_news_event(_vf.NewsEvent(
            title="X", currency="USD", impact="HIGH", event_time=et))
        self.assertTrue(filt.check(0.0001, [0.0001]*20, 0.0001, 0.0001, "EURUSD").can_trade)

    def test_no_events_allowed(self):
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=True)
        filt = _vf.VolatilityFilter(config=cfg)
        self.assertTrue(filt.check(0.0001, [0.0001]*20, 0.0001, 0.0001, "EURUSD").can_trade)

    def test_pr_fail_closed_on_exception(self):
        """Before FIX #6: exception propagated. After: FAIL_CLOSED blocks."""
        mgr = _pr.PortfolioRiskManager()
        with patch.object(mgr, '_check_inner', side_effect=RuntimeError("db down")):
            r = mgr.check(MagicMock(risk_percent=1.0), [])
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)


# ============================================================
# 2. ATR SPIKE ROBUSTNESS
# ============================================================
class TestATRSpikeRobustness(unittest.TestCase):
    """
    Issue: check() had no try/except -> ZeroDivisionError -> gate crash.
    Patch: try/except in check(); fail_mode cached in __init__.
    EURUSD exact thresholds: extreme=3.5 (>=), high=2.0 (>=), spread=3.0 (>).
    Risk: NFP ATR ratio=4.0 -> SL 4x bigger -> 4% actual risk vs 1% sized.
    Compat: check() signature unchanged.
    """

    def _vf(self, fail_mode=None):
        FM = _fm.FailMode
        cfg = _vf.VolatilityFilterConfig(
            enable_news_filter=False,
            fail_mode=FM.FAIL_CLOSED if fail_mode is None else fail_mode)
        return _vf.VolatilityFilter(config=cfg)

    def _check(self, filt, atr_ratio, spread_ratio=1.0, symbol="EURUSD"):
        avg = 0.0010; cur = avg * atr_ratio
        avg_sp = 0.00010; cur_sp = avg_sp * spread_ratio
        return filt.check(cur, [avg]*20, cur_sp, avg_sp, symbol)

    def test_extreme_at_boundary_blocked(self):
        r = self._check(self._vf(), 3.5)
        self.assertFalse(r.can_trade)
        self.assertIn("EXTREME", r.reason)

    def test_below_extreme_allowed(self):
        r = self._check(self._vf(), 3.49)
        self.assertTrue(r.can_trade)
        self.assertEqual(r.level, _vf.VolatilityLevel.HIGH)

    def test_high_at_boundary_lot_mult_one(self):
        r = self._check(self._vf(), 2.0)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.lot_multiplier, 1.0, places=3)

    def test_high_mid_lot_mult_half(self):
        """ratio=2.75 -> lot_mult = 1-(0.75/1.5) = 0.5."""
        r = self._check(self._vf(), 2.75)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.lot_multiplier, 0.5, places=2)

    def test_spread_above_blocked(self):
        r = self._check(self._vf(), 1.0, spread_ratio=3.001)
        self.assertFalse(r.can_trade)
        self.assertIn("SPREAD", r.reason)

    def test_spread_at_limit_allowed(self):
        r = self._check(self._vf(), 1.0, spread_ratio=3.0)
        self.assertTrue(r.can_trade)

    def test_exception_fail_closed(self):
        filt = self._vf()
        with patch.object(filt, '_check_inner', side_effect=ZeroDivisionError("0")):
            r = filt.check(0.0001, [], 0.0001, 0.0001, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_exception_fail_open(self):
        filt = self._vf(fail_mode=_fm.FailMode.FAIL_OPEN)
        with patch.object(filt, '_check_inner', side_effect=ZeroDivisionError("0")):
            r = filt.check(0.0001, [], 0.0001, 0.0001, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_empty_history_fallback(self):
        r = self._vf().check(0.0015, [], 0.0001, 0.0001, "EURUSD")
        self.assertTrue(r.can_trade)
        self.assertEqual(r.level, _vf.VolatilityLevel.NORMAL)

    def test_normal_atr_allowed(self):
        r = self._check(self._vf(), 1.0)
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.lot_multiplier, 1.0, places=3)

    def test_fail_mode_cached_in_init(self):
        filt = self._vf()
        self.assertTrue(hasattr(filt, '_fail_mode'))
        self.assertEqual(filt._fail_mode.value, "FAIL_CLOSED")


# ============================================================
# 3. SYMBOL-SPECIFIC THRESHOLDS
# ============================================================
class TestSymbolSpecificThresholds(unittest.TestCase):
    """
    Issue: Global extreme=3.5 for all assets -> BTC false blocks, Gold false negatives.
    Patch: _DEFAULT_SYMBOL_THRESHOLDS per-asset: XAUUSD=3.0, BTCUSD=2.2, GBPJPY=4.2.
    Risk: BTC blocked on every normal news day / Gold passed during flash crash.
    Compat: VolatilityFilter API unchanged; thresholds are internal lookup.
    """

    def _check(self, ratio, symbol):
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=False)
        filt = _vf.VolatilityFilter(config=cfg)
        avg = 0.001
        return filt.check(avg*ratio, [avg]*20, 0.0001, 0.0001, symbol)

    def test_xauusd_blocked_above_3(self):
        self.assertFalse(self._check(3.1, "XAUUSD").can_trade)

    def test_xauusd_allowed_below_3(self):
        self.assertTrue(self._check(2.9, "XAUUSD").can_trade)

    def test_btcusd_blocked_above_2_2(self):
        self.assertFalse(self._check(2.3, "BTCUSD").can_trade)

    def test_btcusd_allowed_below_2_2(self):
        self.assertTrue(self._check(2.1, "BTCUSD").can_trade)

    def test_eurusd_blocked_at_3_5(self):
        self.assertFalse(self._check(3.5, "EURUSD").can_trade)

    def test_ratio_3_eurusd_allowed_xauusd_blocked(self):
        self.assertTrue(self._check(3.0, "EURUSD").can_trade)
        self.assertFalse(self._check(3.0, "XAUUSD").can_trade)

    def test_gbpjpy_allowed_below_4_2(self):
        self.assertTrue(self._check(4.0, "GBPJPY").can_trade)

    def test_gbpjpy_blocked_at_4_2(self):
        self.assertFalse(self._check(4.2, "GBPJPY").can_trade)

    def test_unknown_symbol_config_default(self):
        self.assertTrue(self._check(3.4, "XXXXXX").can_trade)
        self.assertFalse(self._check(3.5, "XXXXXX").can_trade)


# ============================================================
# 4. GOLD PIP VALUE
# ============================================================
class TestGoldPipValue(unittest.TestCase):
    """
    Issue: XAUUSD=10.0 in both modules (10x wrong).
    Patch: both tables set 'XAUUSD': 1.0.
    Risk: pip=10 -> lot_sizer 10x undersized; OR risk gate 10x inflated.
    Compat: No API changes, only constant value corrected.
    """
    LS = _ls._PIP_VALUE_TABLE
    PR = _pr._PIP_VALUE_TABLE

    def test_ls_xauusd_is_1(self):
        self.assertAlmostEqual(self.LS["XAUUSD"], 1.0, places=5,
                               msg="lot_sizing XAUUSD pip was 10.0, must be 1.0")

    def test_pr_xauusd_is_1(self):
        self.assertAlmostEqual(self.PR["XAUUSD"], 1.0, places=5)

    def test_xauusd_not_10(self):
        self.assertNotAlmostEqual(self.LS["XAUUSD"], 10.0, places=1)

    def test_gold_alias(self):
        val, _ = _run(_ls.LotSizer().get_pip_value("GOLD"))
        self.assertAlmostEqual(val, 1.0, places=5)

    def test_xauusdm_suffix(self):
        val, _ = _run(_ls.LotSizer().get_pip_value("XAUUSDm"))
        self.assertAlmostEqual(val, 1.0, places=5)

    def test_pr_gold_alias(self):
        self.assertAlmostEqual(_pr._get_pip_value("GOLD"), 1.0, places=5)

    def test_risk_pct_1_pct(self):
        """dist=100, lot=1, pip=1, bal=10000 -> risk=1.0% (NOT 10%)."""
        t = _make_trade("XAUUSD", "BUY", 1.0, 1900.0, 1800.0, 10_000.0)
        self.assertAlmostEqual(t.risk_percent, 1.0, places=4)

    def test_risk_pct_not_10(self):
        t = _make_trade("XAUUSD", "BUY", 1.0, 1900.0, 1800.0, 10_000.0)
        self.assertLess(t.risk_percent, 5.0)

    def test_gate_2pct_allowed(self):
        """lot=2.0 -> risk=2.0% = limit -> allowed (strictly >)."""
        t = _make_trade("XAUUSD", "BUY", 2.0, 1900.0, 1800.0, 10_000.0)
        self.assertTrue(_pr.PortfolioRiskManager().check(t, []).can_trade)

    def test_xagusd_pip_50(self):
        self.assertAlmostEqual(self.LS.get("XAGUSD", 0), 50.0, places=1)

    def test_lot_sizer_reasonable(self):
        """1%, $10k, 50-pip -> lot=2.0 (not 0.2 with old pip=10)."""
        r = _run(_ls.LotSizer().calculate(
            10_000.0, 50.0, "XAUUSD", override_risk_pct=1.0))
        self.assertGreater(r.lot_size, 0.5)

    def test_tables_consistent(self):
        self.assertAlmostEqual(self.LS["XAUUSD"], self.PR["XAUUSD"], places=5)


# ============================================================
# 5. CRYPTO PIP VALUE
# ============================================================
class TestCryptoPipValue(unittest.TestCase):
    """
    Issue: ETHUSD pip=0.01 -> lot 100x oversized -> account blown.
    Patch: BTCUSD=ETHUSD=LTCUSD=XRPUSD=1.0 in both modules.
    Risk: 1% risk, $10k, 200-pip SL: pip=0.01 -> lot=500 (should be 0.5).
    Compat: No API changes.
    """
    LS = _ls._PIP_VALUE_TABLE
    PR = _pr._PIP_VALUE_TABLE

    def _both(self, sym):
        self.assertAlmostEqual(self.LS.get(sym, -1), 1.0, places=5)
        self.assertAlmostEqual(self.PR.get(sym, -1), 1.0, places=5)

    def test_btcusd(self): self._both("BTCUSD")
    def test_ethusd(self): self._both("ETHUSD")
    def test_ltcusd(self): self._both("LTCUSD")
    def test_xrpusd(self): self._both("XRPUSD")

    def test_btc_alias(self):
        val, _ = _run(_ls.LotSizer().get_pip_value("BTC"))
        self.assertAlmostEqual(val, 1.0, places=5)

    def test_eth_alias(self):
        val, _ = _run(_ls.LotSizer().get_pip_value("ETH"))
        self.assertAlmostEqual(val, 1.0, places=5)

    def test_btcusdm(self):
        val, _ = _run(_ls.LotSizer().get_pip_value("BTCUSDm"))
        self.assertAlmostEqual(val, 1.0, places=5)

    def test_ethusd_not_001(self):
        self.assertNotAlmostEqual(self.LS.get("ETHUSD", 1.0), 0.01, places=3)

    def test_btc_risk_correct(self):
        """dist=1000, lot=0.1, pip=1, bal=10000 -> 1.0%."""
        t = _make_trade("BTCUSD", "BUY", 0.1, 50_000.0, 49_000.0, 10_000.0)
        self.assertAlmostEqual(t.risk_percent, 1.0, places=4)

    def test_eth_risk_not_100x(self):
        t = _make_trade("ETHUSD", "BUY", 0.1, 3000.0, 2900.0, 10_000.0)
        self.assertGreater(t.risk_percent, 0.05)

    def test_lot_sizer_reasonable(self):
        r = _run(_ls.LotSizer().calculate(
            10_000.0, 500.0, "BTCUSD", override_risk_pct=1.0))
        self.assertGreater(r.lot_size, 0.0)
        self.assertLess(r.lot_size, 5.0)

    def test_tables_consistent(self):
        for sym in ("BTCUSD", "ETHUSD", "LTCUSD", "XRPUSD"):
            self.assertAlmostEqual(self.LS.get(sym,-1), self.PR.get(sym,-1), places=5)


# ============================================================
# 6. EXPOSURE CALCULATION
# ============================================================
class TestExposureCalculation(unittest.TestCase):
    """
    Issue A (FIX #5): hardcoded new_risk=1.0 -> real 2.5% only checked as 1.0%.
    Issue B (FIX #6): no try/except -> corrupt position data propagated.
    3 limits (all strictly >): total=5%, symbol=2%, simultaneous=5, buy=3.
    Compat: check() signature unchanged.
    """

    def _eng(self, **kw):
        return _ec.ExposureControlEngine(
            config=_ec.ExposureControlConfig(**kw))

    def test_total_blocked(self):
        ops = [_make_ep("EURUSD","BUY",1.0), _make_ep("GBPUSD","BUY",1.0),
               _make_ep("AUDUSD","SELL",1.0), _make_ep("NZDUSD","SELL",1.0)]
        r = self._eng().check("CADJPY", "BUY", 1.5, ops)
        self.assertFalse(r.can_trade)
        self.assertIn("Total", r.reason)

    def test_total_boundary_allowed(self):
        """5.0% = limit, strictly > -> allowed."""
        eng = _ec.ExposureControlEngine(config=_ec.ExposureControlConfig(
            max_per_currency_percent=99.0))
        ops = [_make_ep("EURUSD","BUY",1.0), _make_ep("GBPUSD","BUY",1.0),
               _make_ep("AUDUSD","SELL",1.0), _make_ep("NZDUSD","SELL",1.0)]
        r = eng.check("CADJPY", "BUY", 1.0, ops)
        self.assertTrue(r.can_trade, f"5.0%=limit allowed. reason={r.reason}")

    def test_symbol_blocked(self):
        r = self._eng().check("EURUSD", "BUY", 1.0,
                              [_make_ep("EURUSD","SELL",1.5)])
        self.assertFalse(r.can_trade)
        self.assertIn("EURUSD", r.reason)

    def test_symbol_boundary_allowed(self):
        r = self._eng().check("EURUSD", "BUY", 1.0,
                              [_make_ep("EURUSD","SELL",1.0)])
        self.assertTrue(r.can_trade, f"2.0%=limit allowed. reason={r.reason}")

    def test_max_trades_blocked(self):
        eng = _ec.ExposureControlEngine(config=_ec.ExposureControlConfig(
            max_per_currency_percent=99.0))
        ops = [_make_ep(f"P{i}JPY", "BUY" if i%2==0 else "SELL", 0.1)
               for i in range(5)]
        self.assertFalse(eng.check("CADJPY", "BUY", 0.1, ops).can_trade)

    def test_max_trades_boundary_allowed(self):
        eng = _ec.ExposureControlEngine(config=_ec.ExposureControlConfig(
            max_per_currency_percent=99.0))
        ops = [_make_ep(f"P{i}JPY", "BUY" if i%2==0 else "SELL", 0.1)
               for i in range(4)]
        r = eng.check("CADJPY", "BUY", 0.1, ops)
        self.assertTrue(r.can_trade, f"4+1=5=limit. reason={r.reason}")

    def test_max_buy_blocked(self):
        eng = _ec.ExposureControlEngine(config=_ec.ExposureControlConfig(
            max_per_currency_percent=99.0))
        ops = [_make_ep("EURUSD","BUY",0.5), _make_ep("GBPUSD","BUY",0.5),
               _make_ep("AUDUSD","BUY",0.5)]
        r = eng.check("NZDUSD", "BUY", 0.5, ops)
        self.assertFalse(r.can_trade)
        self.assertIn("BUY", r.reason)

    def test_duplicate_blocked(self):
        r = self._eng().check("EURUSD", "BUY", 0.5,
                              [_make_ep("EURUSD","BUY",1.0)])
        self.assertFalse(r.can_trade)
        self.assertIn("Duplicate", r.reason)

    def test_real_risk_fix5(self):
        """FIX #5: projected must be 2.5%, not hardcoded 1.0%."""
        eng = _ec.ExposureControlEngine(config=_ec.ExposureControlConfig(
            max_per_currency_percent=99.0))
        r = eng.check("CADJPY", "BUY", 2.5, [])
        self.assertAlmostEqual(r.projected_total_risk, 2.5, places=3)

    def test_fail_closed_blocks(self):
        eng = self._eng()
        with patch.object(eng, '_check_inner', side_effect=AttributeError("x")):
            self.assertFalse(eng.check("EURUSD", "BUY", 1.0, []).can_trade)

    def test_fail_open_allows(self):
        eng = _ec.ExposureControlEngine(fail_mode=_fm.FailMode.FAIL_OPEN)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError("x")):
            self.assertTrue(eng.check("EURUSD", "BUY", 1.0, []).can_trade)

    def test_get_snapshot_normal(self):
        snap = self._eng().get_snapshot([_make_ep("EURUSD","BUY",1.0)])
        self.assertAlmostEqual(snap.total_risk_percent, 1.0, places=4)

    def test_empty_allowed(self):
        self.assertTrue(self._eng().check("EURUSD", "BUY", 1.0, []).can_trade)


# ============================================================
# 7. FAIL-CLOSED BEHAVIOUR
# ============================================================
class TestFailClosedBehaviour(unittest.TestCase):
    """
    Issue: CF had silent FAIL_OPEN; EC/VF/PR had no try/except.
    Patch: All 4 gates wrapped; all exceptions logged; never silent.
    Risk: Silent pass = undetected blowup scenario.
    Compat: All public check() signatures unchanged.
    """

    def test_ssot_vf(self):
        self.assertEqual(_vf.FailMode.FAIL_CLOSED.value, "FAIL_CLOSED")
        self.assertEqual(_vf.FailMode.FAIL_OPEN.value,   "FAIL_OPEN")

    def test_ssot_ec(self):
        self.assertEqual(_ec.FailMode.FAIL_CLOSED.value, "FAIL_CLOSED")

    def test_ssot_cf(self):
        self.assertEqual(_cf.FailMode.FAIL_CLOSED.value, "FAIL_CLOSED")

    def test_ssot_pr(self):
        self.assertEqual(_pr.FailMode.FAIL_CLOSED.value, "FAIL_CLOSED")

    def test_ssot_canonical(self):
        self.assertEqual(_fm.FailMode.FAIL_CLOSED.value, "FAIL_CLOSED")
        self.assertEqual(_fm.FailMode.FAIL_OPEN.value,   "FAIL_OPEN")

    def test_vf_default_fail_closed(self):
        self.assertEqual(_vf.VolatilityFilter()._fail_mode.value, "FAIL_CLOSED")

    def test_ec_default_fail_closed(self):
        self.assertEqual(_ec.ExposureControlEngine()._fail_mode.value, "FAIL_CLOSED")

    def test_cf_default_fail_closed(self):
        self.assertEqual(_cf.CorrelationFilter()._fail_mode.value, "FAIL_CLOSED")

    def test_pr_default_fail_closed(self):
        self.assertEqual(_pr.PortfolioRiskManager()._fail_mode.value, "FAIL_CLOSED")

    def test_coerce_lower(self):
        self.assertIs(_fm.coerce("fail_closed"), _fm.FailMode.FAIL_CLOSED)

    def test_coerce_upper(self):
        self.assertIs(_fm.coerce("FAIL_OPEN"), _fm.FailMode.FAIL_OPEN)

    def test_coerce_passthrough(self):
        self.assertIs(_fm.coerce(_fm.FailMode.FAIL_CLOSED), _fm.FailMode.FAIL_CLOSED)

    def test_vf_logs_error(self):
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=False,
                                         fail_mode=_fm.FailMode.FAIL_CLOSED)
        filt = _vf.VolatilityFilter(config=cfg)
        with patch.object(filt, '_check_inner', side_effect=ValueError("bad")):
            with self.assertLogs("risk.volatility_filter", level=logging.ERROR):
                r = filt.check(0.001, [0.001]*5, 0.0001, 0.0001, "EURUSD")
        self.assertFalse(r.can_trade)

    def test_vf_fail_open_logs_critical(self):
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=False,
                                         fail_mode=_fm.FailMode.FAIL_OPEN)
        filt = _vf.VolatilityFilter(config=cfg)
        with patch.object(filt, '_check_inner', side_effect=ValueError("bad")):
            with self.assertLogs("risk.volatility_filter", level=logging.CRITICAL):
                r = filt.check(0.001, [0.001]*5, 0.0001, 0.0001, "EURUSD")
        self.assertTrue(r.can_trade)

    def test_ec_logs_error(self):
        eng = _ec.ExposureControlEngine()
        with patch.object(eng, '_check_inner', side_effect=AttributeError("null")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                r = eng.check("EURUSD", "BUY", 1.0, [])
        self.assertFalse(r.can_trade)

    def test_ec_fail_open_logs(self):
        eng = _ec.ExposureControlEngine(fail_mode=_fm.FailMode.FAIL_OPEN)
        with patch.object(eng, '_check_inner', side_effect=RuntimeError("gone")):
            with self.assertLogs("risk.exposure", level=logging.ERROR):
                r = eng.check("EURUSD", "BUY", 1.0, [])
        self.assertTrue(r.can_trade)

    def test_cf_logs_critical(self):
        """CF was SILENT before fix. Now must log CRITICAL."""
        cf = _cf.CorrelationFilter()
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("was silent")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                r = _run(cf.check("EURUSD", "BUY", [], 1.0))
        self.assertFalse(r.can_trade)

    def test_cf_fail_open_logs(self):
        cf = _cf.CorrelationFilter(fail_mode=_fm.FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("open")):
            with self.assertLogs("risk.correlation_filter", level=logging.CRITICAL):
                r = _run(cf.check("EURUSD", "BUY", [], 1.0))
        self.assertTrue(r.can_trade)

    def test_pr_logs(self):
        mgr = _pr.PortfolioRiskManager()
        with patch.object(mgr, '_check_inner', side_effect=KeyError("pip")):
            with self.assertLogs(level=logging.ERROR):
                r = mgr.check(MagicMock(risk_percent=1.0), [])
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_pr_fail_open(self):
        mgr = _pr.PortfolioRiskManager(fail_mode=_fm.FailMode.FAIL_OPEN)
        with patch.object(mgr, '_check_inner', side_effect=KeyError("pip")):
            r = mgr.check(MagicMock(risk_percent=1.0), [])
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_vf_kwarg_override(self):
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=False,
                                         fail_mode=_fm.FailMode.FAIL_OPEN)
        self.assertEqual(_vf.VolatilityFilter(config=cfg)._fail_mode.value, "FAIL_OPEN")

    def test_ec_kwarg_override(self):
        self.assertEqual(
            _ec.ExposureControlEngine(fail_mode=_fm.FailMode.FAIL_OPEN)._fail_mode.value,
            "FAIL_OPEN")

    def test_cf_kwarg_override(self):
        self.assertEqual(
            _cf.CorrelationFilter(fail_mode=_fm.FailMode.FAIL_OPEN)._fail_mode.value,
            "FAIL_OPEN")


# ============================================================
# 8. PORTFOLIO CORRELATION CALCULATIONS
# ============================================================
class TestPortfolioCorrelationCalcs(unittest.TestCase):
    """
    Issue: Before FIX #6, outer try/except missing -> crash bypassed fail_mode.
    FIX #4: RollingCorrelationEngine. FIX #6: outer try/except.
    net = corr * dir_factor * risk%; abs>=0.80 BLOCKED; [0.60,0.80) penalty.
    Risk: Silent crash = correlated overexposure allowed.
    Compat: check() signature unchanged.
    """

    def _cf(self, **kw):
        return _cf.CorrelationFilter(config=_cf.CorrelationFilterConfig(**kw))

    def _check(self, cf, sym, dir_, pos, rp=1.0):
        return _run(cf.check(sym, dir_, pos, rp))

    def _mock(self, cf, val):
        return patch.object(cf, '_get_correlation',
                            new=AsyncMock(return_value=(val, "mock")))

    def test_positive_corr_blocked(self):
        cf = self._cf()
        with self._mock(cf, 0.85):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("GBPUSD","BUY",1.0)])
        self.assertFalse(r.can_trade)

    def test_negative_corr_blocked(self):
        cf = self._cf()
        with self._mock(cf, -0.92):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("USDCHF","BUY",1.0)])
        self.assertFalse(r.can_trade)

    def test_at_boundary_blocked(self):
        """abs_net=0.80 >= 0.80 -> blocked (inclusive)."""
        cf = self._cf()
        with self._mock(cf, 0.80):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("GBPUSD","BUY",1.0)])
        self.assertFalse(r.can_trade)

    def test_below_boundary_allowed(self):
        cf = self._cf()
        with self._mock(cf, 0.799):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("GBPUSD","BUY",1.0)])
        self.assertTrue(r.can_trade)

    def test_penalty_zone_mult_reduced(self):
        cf = self._cf()
        with self._mock(cf, 0.70):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("GBPUSD","BUY",1.0)])
        self.assertTrue(r.can_trade)
        self.assertLess(r.risk_multiplier, 1.0)

    def test_below_penalty_mult_one(self):
        cf = self._cf()
        with self._mock(cf, 0.50):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("GBPUSD","BUY",1.0)])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 1.0, places=3)

    def test_opposite_dir_abs_blocked(self):
        """BUY vs SELL: dir=-1, net=-0.85, abs=0.85 -> blocked."""
        cf = self._cf()
        with self._mock(cf, 0.85):
            r = self._check(cf, "EURUSD", "BUY", [_make_cp("GBPUSD","SELL",1.0)])
        self.assertFalse(r.can_trade)

    def test_accumulated_blocked(self):
        """2 * 0.45 * 1% = 0.90 >= 0.80 -> blocked."""
        cf = self._cf()
        with self._mock(cf, 0.45):
            r = self._check(cf, "EURUSD", "BUY",
                            [_make_cp("GBPUSD","BUY",1.0),
                             _make_cp("AUDUSD","BUY",1.0)])
        self.assertFalse(r.can_trade)

    def test_static_eurusd_gbpusd_blocked(self):
        r = self._check(self._cf(), "EURUSD", "BUY",
                        [_make_cp("GBPUSD","BUY",1.0)])
        self.assertFalse(r.can_trade)

    def test_no_positions_allowed(self):
        r = self._check(self._cf(), "EURUSD", "BUY", [])
        self.assertTrue(r.can_trade)
        self.assertAlmostEqual(r.risk_multiplier, 1.0, places=3)

    def test_pearson_identical(self):
        x = [0.001, -0.002, 0.003, 0.001, -0.001] * 3
        self.assertAlmostEqual(_cf._pearson(x, x), 1.0, places=4)

    def test_pearson_mirror(self):
        x = [0.001, -0.002, 0.003, 0.001, -0.001] * 3
        self.assertAlmostEqual(_cf._pearson(x, [-v for v in x]), -1.0, places=4)

    def test_pearson_short(self):
        self.assertAlmostEqual(_cf._pearson([0.1, 0.2], [0.1, 0.2]), 0.0, places=4)

    def test_outer_crash_fail_closed(self):
        cf = self._cf()
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("crash")):
            r = _run(cf.check("EURUSD", "BUY",
                              [_make_cp("GBPUSD","BUY",1.0)], 1.0))
        self.assertFalse(r.can_trade)
        self.assertEqual(r.source, "error")

    def test_outer_crash_fail_open(self):
        cf = _cf.CorrelationFilter(fail_mode=_fm.FailMode.FAIL_OPEN)
        with patch.object(cf, '_check_inner', side_effect=RuntimeError("crash")):
            r = _run(cf.check("EURUSD", "BUY",
                              [_make_cp("GBPUSD","BUY",1.0)], 1.0))
        self.assertTrue(r.can_trade)
        self.assertEqual(r.source, "error")

    def test_canonical_alphabetical(self):
        self.assertEqual(_cf._canonical("GBPUSD", "EURUSD"), ("EURUSD", "GBPUSD"))


# ============================================================
# 9. INTEGRATION
# ============================================================
class TestIntegration(unittest.TestCase):

    def test_nfp_blocked(self):
        cfg = _vf.VolatilityFilterConfig(enable_news_filter=True)
        filt = _vf.VolatilityFilter(config=cfg)
        et = datetime.now(timezone.utc) + timedelta(minutes=5)
        filt.add_news_event(_vf.NewsEvent(
            title="NFP", currency="USD", impact="HIGH", event_time=et))
        r = filt.check(0.003, [0.001]*20, 0.0003, 0.0001, "EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("NEWS", r.reason)

    def test_gold_gate_correct(self):
        mgr = _pr.PortfolioRiskManager()
        t_ok  = _make_trade("XAUUSD","BUY",2.0,1900.0,1800.0,10_000.0)
        t_bad = _make_trade("XAUUSD","BUY",2.5,1900.0,1800.0,10_000.0)
        self.assertTrue(mgr.check(t_ok, []).can_trade)
        self.assertFalse(mgr.check(t_bad, []).can_trade)

    def test_exposure_and_portfolio_pass(self):
        eng = _ec.ExposureControlEngine()
        mgr = _pr.PortfolioRiskManager()
        t = _make_trade("EURUSD","BUY",1.0,1.1,1.09,10_000.0)
        self.assertTrue(eng.check("EURUSD","BUY",t.risk_percent,[]).can_trade)
        self.assertTrue(mgr.check(t, []).can_trade)

    def test_all_four_fail_closed(self):
        self.assertEqual(_vf.VolatilityFilter()._fail_mode.value,      "FAIL_CLOSED")
        self.assertEqual(_ec.ExposureControlEngine()._fail_mode.value, "FAIL_CLOSED")
        self.assertEqual(_cf.CorrelationFilter()._fail_mode.value,     "FAIL_CLOSED")
        self.assertEqual(_pr.PortfolioRiskManager()._fail_mode.value,  "FAIL_CLOSED")

    def test_crypto_lot_reasonable(self):
        r = _run(_ls.LotSizer().calculate(
            10_000.0, 200.0, "BTCUSD", override_risk_pct=1.0))
        self.assertLess(r.lot_size, 10.0)
        self.assertGreater(r.lot_size, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
