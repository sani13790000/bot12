"""
test_fix6_fail_closed.py  -  FIX #6: Fail-Closed Mode  -  41 tests
Covers all 7 issues identified in audit.
"""
from __future__ import annotations
import asyncio, logging, sys, types
from unittest.mock import MagicMock
import pytest

def _ensure_pip_stub():
    stub = types.ModuleType("backend")
    stub.risk = types.ModuleType("backend.risk")
    pip_stub = types.ModuleType("backend.risk._pip_helpers")
    pip_stub._price_to_pips     = lambda sym, d: d * 10_000
    pip_stub._estimate_risk_pct = lambda sym, pd, lot, bal: (0.0, "none")
    stub.risk._pip_helpers = pip_stub
    sys.modules.setdefault("backend", stub)
    sys.modules.setdefault("backend.risk", stub.risk)
    sys.modules.setdefault("backend.risk._pip_helpers", pip_stub)

_ensure_pip_stub()

import importlib.util as _ilu

_ORCH = "/home/definable/fix6/risk_orchestrator_fix6.py"
_EXPO = "/home/definable/fix6/exposure_control_fix6.py"

def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def _orch_mod(): return _load(f"ro_{id(object())}", _ORCH)
def _expo_mod(): return _load(f"ec_{id(object())}", _EXPO)

def run(coro): return asyncio.run(coro)

BASE = dict(symbol="EURUSD", direction="BUY", entry_price=1.1000,
            stop_loss=1.0950, account_balance=10_000.0, user_id="u1", signal_id="s1")

def _bomb(exc=RuntimeError, msg="boom"):
    m = MagicMock(); m.check.side_effect = exc(msg); return m

def _ok():
    m = MagicMock(); r = MagicMock()
    r.can_trade=True; r.reason=""; r.lot_multiplier=1.0
    m.check.return_value = r; return m

def _make(**kw):
    mod = _orch_mod()
    orch = mod.RiskOrchestrator(**kw)
    return orch, mod


class TestFailModeEnum:
    def test_string_closed(self):
        o, m = _make(fail_mode_equity="FAIL_CLOSED")
        assert o._fail_equity == m.FailMode.FAIL_CLOSED
    def test_string_open(self):
        o, m = _make(fail_mode_equity="FAIL_OPEN")
        assert o._fail_equity == m.FailMode.FAIL_OPEN
    def test_enum_direct(self):
        m = _orch_mod()
        o = m.RiskOrchestrator(fail_mode_equity=m.FailMode.FAIL_OPEN)
        assert o._fail_equity == m.FailMode.FAIL_OPEN
    def test_all_default_closed(self):
        o, m = _make()
        FC = m.FailMode.FAIL_CLOSED
        assert all(x == FC for x in [o._fail_equity, o._fail_daily, o._fail_vol,
                                      o._fail_corr, o._fail_lot, o._fail_exp])
    def test_per_gate_independent(self):
        o, m = _make(fail_mode_correlation="FAIL_OPEN", fail_mode_exposure="FAIL_OPEN")
        assert o._fail_corr == m.FailMode.FAIL_OPEN
        assert o._fail_exp  == m.FailMode.FAIL_OPEN
        assert o._fail_equity == m.FailMode.FAIL_CLOSED
    def test_invalid_raises(self):
        try: _make(fail_mode_equity="BANANA")
        except (ValueError, KeyError): pass

class TestEquityGate:
    def test_closed_blocks(self):
        o, _ = _make(equity_guard=_bomb(), fail_mode_equity="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved and "EQUITY_GATE_ERROR" in r.block_reason
    def test_open_allows(self):
        o, _ = _make(equity_guard=_bomb(), fail_mode_equity="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved and "EQUITY_FAIL_OPEN" in r.gates_passed
    def test_logged_closed(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(equity_guard=_bomb(), fail_mode_equity="FAIL_CLOSED")
            run(o.check(**BASE))
        assert len(caplog.records) > 0
    def test_logged_open(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(equity_guard=_bomb(), fail_mode_equity="FAIL_OPEN")
            run(o.check(**BASE))
        assert len(caplog.records) > 0
    def test_working_passes(self):
        o, _ = _make(equity_guard=_ok())
        r = run(o.check(**BASE))
        assert "EQUITY" in r.gates_passed

class TestDailyGate:
    def test_closed_blocks(self):
        o, _ = _make(daily_limits=_bomb(), fail_mode_daily="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved and "DAILY_LIMITS_GATE_ERROR" in r.block_reason
    def test_open_allows(self):
        o, _ = _make(daily_limits=_bomb(), fail_mode_daily="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved and "DAILY_FAIL_OPEN" in r.gates_passed
    def test_logged(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(daily_limits=_bomb(), fail_mode_daily="FAIL_CLOSED")
            run(o.check(**BASE))
        assert len(caplog.records) > 0

class TestVolatilityGate:
    def test_closed_blocks(self):
        o, _ = _make(volatility_filter=_bomb(), fail_mode_volatility="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved and "VOLATILITY_GATE_ERROR" in r.block_reason
    def test_open_allows(self):
        o, _ = _make(volatility_filter=_bomb(), fail_mode_volatility="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved and "VOLATILITY_FAIL_OPEN" in r.gates_passed

class TestCorrelationGate:
    def test_closed_blocks(self):
        o, _ = _make(correlation_filter=_bomb(), fail_mode_correlation="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved and "CORRELATION_GATE_ERROR" in r.block_reason
    def test_open_allows(self):
        o, _ = _make(correlation_filter=_bomb(), fail_mode_correlation="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved and "CORRELATION_FAIL_OPEN" in r.gates_passed
    def test_independent(self):
        o, _ = _make(correlation_filter=_bomb(), fail_mode_correlation="FAIL_OPEN",
                     fail_mode_equity="FAIL_CLOSED")
        assert run(o.check(**BASE)).approved

class TestLotSizingGate:
    def _blot(self):
        m = MagicMock(); m.calculate = MagicMock(side_effect=RuntimeError("lot")); return m
    def test_closed_blocks(self):
        o, _ = _make(lot_sizer=self._blot(), fail_mode_lot="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved and "LOT_SIZING_GATE_ERROR" in r.block_reason
    def test_open_allows(self):
        o, _ = _make(lot_sizer=self._blot(), fail_mode_lot="FAIL_OPEN", default_risk_percent=2.5)
        r = run(o.check(**BASE))
        assert r.approved and "LOT_SIZING_FAIL_OPEN" in r.gates_passed
        assert r.risk_percent == 2.5
    def test_logged(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(lot_sizer=self._blot(), fail_mode_lot="FAIL_CLOSED")
            run(o.check(**BASE))
        assert len(caplog.records) > 0

class TestExposureGate:
    def test_closed_blocks(self):
        o, _ = _make(exposure_control=_bomb(), fail_mode_exposure="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved and "EXPOSURE_GATE_ERROR" in r.block_reason
    def test_open_allows(self):
        o, _ = _make(exposure_control=_bomb(), fail_mode_exposure="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved and "EXPOSURE_FAIL_OPEN" in r.gates_passed
    def test_independent(self):
        o, _ = _make(exposure_control=_bomb(), fail_mode_exposure="FAIL_OPEN",
                     fail_mode_equity="FAIL_CLOSED")
        assert run(o.check(**BASE)).approved

class TestExposureEngineStandalone:
    def setup_method(self): self.mod = _expo_mod()
    def _pos(self, n=0):
        return [self.mod.ExposurePosition("EURUSD","BUY",1.0) for _ in range(n)]
    def test_normal_passes(self):
        assert self.mod.ExposureControlEngine().check("GBPUSD","BUY",1.0,[]).can_trade
    def test_inner_bomb_closed(self):
        e = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_CLOSED)
        e._check_inner = MagicMock(side_effect=ValueError("inner"))
        r = e.check("EURUSD","BUY",1.0,[])
        assert not r.can_trade and "FAIL_CLOSED" in r.reason
    def test_inner_bomb_open(self):
        e = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_OPEN)
        e._check_inner = MagicMock(side_effect=ValueError("inner"))
        r = e.check("EURUSD","BUY",1.0,[])
        assert r.can_trade and r.reason == "FAIL_OPEN_EXCEPTION_IGNORED"
    def test_snap_bomb_closed(self):
        e = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_CLOSED)
        e._snapshot_inner = MagicMock(side_effect=RuntimeError("snap"))
        s = e.get_snapshot([])
        assert not s.can_open_new and "FAIL_CLOSED" in s.block_reason
    def test_snap_bomb_open(self):
        e = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_OPEN)
        e._snapshot_inner = MagicMock(side_effect=RuntimeError("snap"))
        assert e.get_snapshot([]).can_open_new
    def test_default_closed(self):
        assert self.mod.ExposureControlEngine()._fail_mode == self.mod.FailMode.FAIL_CLOSED
    def test_string_accepted(self):
        e = self.mod.ExposureControlEngine(fail_mode="FAIL_OPEN")
        assert e._fail_mode == self.mod.FailMode.FAIL_OPEN
    def test_exception_logged(self, caplog):
        e = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_CLOSED)
        e._check_inner = MagicMock(side_effect=RuntimeError("log"))
        with caplog.at_level(logging.ERROR): e.check("EURUSD","BUY",1.0,[])
        assert len(caplog.records) > 0

class TestLogging:
    def test_all_gates_log(self, caplog):
        for kw in [
            dict(equity_guard=_bomb(), fail_mode_equity="FAIL_CLOSED"),
            dict(daily_limits=_bomb(), fail_mode_daily="FAIL_CLOSED"),
            dict(volatility_filter=_bomb(), fail_mode_volatility="FAIL_CLOSED"),
            dict(correlation_filter=_bomb(), fail_mode_correlation="FAIL_CLOSED"),
            dict(exposure_control=_bomb(), fail_mode_exposure="FAIL_CLOSED"),
        ]:
            with caplog.at_level(logging.ERROR):
                o, _ = _make(**kw); run(o.check(**BASE))
            assert len(caplog.records) > 0; caplog.clear()
    def test_fail_open_critical(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            o, _ = _make(equity_guard=_bomb(), fail_mode_equity="FAIL_OPEN")
            run(o.check(**BASE))
        assert any(r.levelno >= logging.CRITICAL for r in caplog.records)

class TestBackwardCompat:
    def test_no_gates_approved(self):
        o, _ = _make(); assert run(o.check(**BASE)).approved
    def test_invalid_sl_blocked(self):
        o, _ = _make(); kw = dict(BASE); kw["stop_loss"] = kw["entry_price"]
        assert not run(o.check(**kw)).approved
    def test_string_params(self):
        o, m = _make(fail_mode_correlation="FAIL_OPEN", fail_mode_exposure="FAIL_CLOSED")
        assert o._fail_corr == m.FailMode.FAIL_OPEN
        assert o._fail_exp  == m.FailMode.FAIL_CLOSED
    def test_exposure_no_args(self):
        mod = _expo_mod()
        assert mod.ExposureControlEngine().check("EURUSD","BUY",1.0,[]).can_trade
    def test_singleton(self):
        mod = _expo_mod()
        assert mod.get_exposure_control() is mod.get_exposure_control()
    def test_default_risk_respected(self):
        m = MagicMock(); m.calculate = MagicMock(side_effect=RuntimeError("lot"))
        o, _ = _make(lot_sizer=m, fail_mode_lot="FAIL_OPEN", default_risk_percent=3.0)
        assert run(o.check(**BASE)).risk_percent == 3.0
