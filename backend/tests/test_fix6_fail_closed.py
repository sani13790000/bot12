"""
test_fix6_fail_closed.py
FIX #6: Fail-Closed Mode - 41 tests
Groups:
  1.  FailMode enum coercion               (6 tests)
  2.  EQUITY gate fail_mode                (5 tests)
  3.  DAILY gate fail_mode                 (3 tests)
  4.  VOLATILITY gate fail_mode            (2 tests)
  5.  CORRELATION gate fail_mode           (3 tests)
  6.  LOT_SIZING gate fail_mode            (3 tests)
  7.  EXPOSURE gate fail_mode              (3 tests)
  8.  ExposureControlEngine standalone     (8 tests)
  9.  Logging always occurs                (2 tests)
  10. Backward compatibility               (6 tests)
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

_ORCH_PATH = "/home/definable/fix6/risk_orchestrator_fix6.py"
_EXPO_PATH = "/home/definable/fix6/exposure_control_fix6.py"


def _load(name, path):
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _orch_mod():
    return _load(f"risk_orch_{id(object())}", _ORCH_PATH)


def _expo_mod():
    return _load(f"expo_ctrl_{id(object())}", _EXPO_PATH)


def run(coro):
    return asyncio.run(coro)


BASE = dict(
    symbol="EURUSD", direction="BUY",
    entry_price=1.1000, stop_loss=1.0950,
    account_balance=10_000.0,
    user_id="u1", signal_id="s1",
)


def _bomb(exc=RuntimeError, msg="boom"):
    m = MagicMock()
    m.check.side_effect = exc(msg)
    return m


def _ok_gate(can_trade=True):
    m = MagicMock()
    r = MagicMock()
    r.can_trade = can_trade; r.reason = ""; r.lot_multiplier = 1.0
    m.check.return_value = r
    return m


def _make(
    equity=None, daily=None, vol=None, corr=None, expo=None, lot=None,
    fail_mode_equity="FAIL_CLOSED",
    fail_mode_daily="FAIL_CLOSED",
    fail_mode_volatility="FAIL_CLOSED",
    fail_mode_correlation="FAIL_CLOSED",
    fail_mode_lot="FAIL_CLOSED",
    fail_mode_exposure="FAIL_CLOSED",
    default_risk_percent=1.0,
):
    mod = _orch_mod()
    orch = mod.RiskOrchestrator(
        equity_guard=equity, daily_limits=daily,
        volatility_filter=vol, correlation_filter=corr,
        exposure_control=expo, lot_sizer=lot,
        fail_mode_equity=fail_mode_equity,
        fail_mode_daily=fail_mode_daily,
        fail_mode_volatility=fail_mode_volatility,
        fail_mode_correlation=fail_mode_correlation,
        fail_mode_lot=fail_mode_lot,
        fail_mode_exposure=fail_mode_exposure,
        default_risk_percent=default_risk_percent,
    )
    return orch, mod


class TestFailModeEnum:
    def test_string_closed_coerced_to_enum(self):
        o, m = _make(fail_mode_equity="FAIL_CLOSED")
        assert o._fail_equity == m.FailMode.FAIL_CLOSED

    def test_string_open_coerced_to_enum(self):
        o, m = _make(fail_mode_equity="FAIL_OPEN")
        assert o._fail_equity == m.FailMode.FAIL_OPEN

    def test_enum_value_accepted_directly(self):
        m = _orch_mod()
        o = m.RiskOrchestrator(fail_mode_equity=m.FailMode.FAIL_OPEN)
        assert o._fail_equity == m.FailMode.FAIL_OPEN

    def test_all_gates_default_to_closed(self):
        o, m = _make()
        FC = m.FailMode.FAIL_CLOSED
        assert o._fail_equity == FC
        assert o._fail_daily  == FC
        assert o._fail_vol    == FC
        assert o._fail_corr   == FC
        assert o._fail_lot    == FC
        assert o._fail_exp    == FC

    def test_per_gate_independently_configurable(self):
        o, m = _make(fail_mode_correlation="FAIL_OPEN", fail_mode_exposure="FAIL_OPEN")
        assert o._fail_corr   == m.FailMode.FAIL_OPEN
        assert o._fail_exp    == m.FailMode.FAIL_OPEN
        assert o._fail_equity == m.FailMode.FAIL_CLOSED

    def test_invalid_string_raises_or_defaults(self):
        try:
            o, m = _make(fail_mode_equity="INVALID_MODE")
            assert o._fail_equity == m.FailMode.FAIL_CLOSED
        except ValueError:
            pass


class TestEquityGate:
    def test_closed_blocks_on_exception(self):
        o, _ = _make(equity=_bomb(), fail_mode_equity="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "EQUITY_GATE_ERROR" in r.block_reason

    def test_open_allows_on_exception(self):
        o, _ = _make(equity=_bomb(), fail_mode_equity="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved
        assert "EQUITY_FAIL_OPEN" in r.gates_passed

    def test_exception_always_logged_closed(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(equity=_bomb(), fail_mode_equity="FAIL_CLOSED")
            run(o.check(**BASE))
        assert any("EQUITY" in rec.message or "equity" in rec.message.lower() for rec in caplog.records)

    def test_exception_always_logged_open(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(equity=_bomb(), fail_mode_equity="FAIL_OPEN")
            run(o.check(**BASE))
        assert len(caplog.records) > 0

    def test_working_equity_gate_passes(self):
        o, _ = _make(equity=_ok_gate(can_trade=True))
        r = run(o.check(**BASE))
        assert "EQUITY" in r.gates_passed


class TestDailyGate:
    def test_closed_blocks_on_exception(self):
        o, _ = _make(daily=_bomb(), fail_mode_daily="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "DAILY_LIMITS_GATE_ERROR" in r.block_reason

    def test_open_allows_on_exception(self):
        o, _ = _make(daily=_bomb(), fail_mode_daily="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved
        assert "DAILY_FAIL_OPEN" in r.gates_passed

    def test_exception_logged_daily(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(daily=_bomb(), fail_mode_daily="FAIL_CLOSED")
            run(o.check(**BASE))
        assert len(caplog.records) > 0


class TestVolatilityGate:
    def test_closed_blocks_on_exception(self):
        o, _ = _make(vol=_bomb(), fail_mode_volatility="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "VOLATILITY_GATE_ERROR" in r.block_reason

    def test_open_allows_on_exception(self):
        o, _ = _make(vol=_bomb(), fail_mode_volatility="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved
        assert "VOLATILITY_FAIL_OPEN" in r.gates_passed


class TestCorrelationGate:
    def test_closed_blocks_on_exception(self):
        o, _ = _make(corr=_bomb(), fail_mode_correlation="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "CORRELATION_GATE_ERROR" in r.block_reason

    def test_open_allows_on_exception(self):
        o, _ = _make(corr=_bomb(), fail_mode_correlation="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved
        assert "CORRELATION_FAIL_OPEN" in r.gates_passed

    def test_corr_independent_from_equity(self):
        o, _ = _make(corr=_bomb(), fail_mode_correlation="FAIL_OPEN", fail_mode_equity="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert r.approved


class TestLotSizingGate:
    def _bomb_lot(self):
        m = MagicMock()
        m.calculate = MagicMock(side_effect=RuntimeError("lot bomb"))
        return m

    def test_closed_blocks_on_exception(self):
        o, _ = _make(lot=self._bomb_lot(), fail_mode_lot="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "LOT_SIZING_GATE_ERROR" in r.block_reason

    def test_open_allows_with_fallback_risk(self):
        o, _ = _make(lot=self._bomb_lot(), fail_mode_lot="FAIL_OPEN", default_risk_percent=2.5)
        r = run(o.check(**BASE))
        assert r.approved
        assert "LOT_SIZING_FAIL_OPEN" in r.gates_passed

    def test_lot_exception_logged(self, caplog):
        with caplog.at_level(logging.ERROR):
            o, _ = _make(lot=self._bomb_lot(), fail_mode_lot="FAIL_CLOSED")
            run(o.check(**BASE))
        assert len(caplog.records) > 0


class TestExposureGate:
    def test_closed_blocks_on_exception(self):
        o, _ = _make(expo=_bomb(), fail_mode_exposure="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "EXPOSURE_GATE_ERROR" in r.block_reason

    def test_open_allows_on_exception(self):
        o, _ = _make(expo=_bomb(), fail_mode_exposure="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved
        assert "EXPOSURE_FAIL_OPEN" in r.gates_passed

    def test_exposure_independent_from_other_gates(self):
        o, _ = _make(expo=_bomb(), fail_mode_equity="FAIL_CLOSED", fail_mode_exposure="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved


class TestExposureEngineStandalone:
    def setup_method(self):
        self.mod = _expo_mod()

    def test_normal_check_passes_unaffected(self):
        eng = self.mod.ExposureControlEngine()
        r = eng.check("GBPUSD", "BUY", 1.0, [])
        assert r.can_trade

    def test_inner_exception_fail_closed_blocks(self):
        eng = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_CLOSED)
        eng._check_inner = MagicMock(side_effect=ValueError("inner"))
        r = eng.check("EURUSD", "BUY", 1.0, [])
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_inner_exception_fail_open_allows(self):
        eng = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_OPEN)
        eng._check_inner = MagicMock(side_effect=ValueError("inner"))
        r = eng.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade
        assert r.reason == "FAIL_OPEN_EXCEPTION_IGNORED"

    def test_snapshot_exception_fail_closed(self):
        eng = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_CLOSED)
        eng._snapshot_inner = MagicMock(side_effect=RuntimeError("snap"))
        s = eng.get_snapshot([])
        assert not s.can_open_new
        assert "FAIL_CLOSED" in s.block_reason

    def test_snapshot_exception_fail_open(self):
        eng = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_OPEN)
        eng._snapshot_inner = MagicMock(side_effect=RuntimeError("snap"))
        s = eng.get_snapshot([])
        assert s.can_open_new

    def test_default_fail_mode_is_closed(self):
        eng = self.mod.ExposureControlEngine()
        assert eng._fail_mode == self.mod.FailMode.FAIL_CLOSED

    def test_fail_mode_string_accepted(self):
        eng = self.mod.ExposureControlEngine(fail_mode="FAIL_OPEN")
        assert eng._fail_mode == self.mod.FailMode.FAIL_OPEN

    def test_exception_logged_on_check_error(self, caplog):
        eng = self.mod.ExposureControlEngine(fail_mode=self.mod.FailMode.FAIL_CLOSED)
        eng._check_inner = MagicMock(side_effect=RuntimeError("log-test"))
        with caplog.at_level(logging.ERROR):
            eng.check("EURUSD", "BUY", 1.0, [])
        assert len(caplog.records) > 0


class TestLoggingAlwaysOccurs:
    def test_every_gate_logs_on_exception(self, caplog):
        gates = [
            dict(equity=_bomb(), fail_mode_equity="FAIL_CLOSED"),
            dict(daily=_bomb(), fail_mode_daily="FAIL_CLOSED"),
            dict(vol=_bomb(), fail_mode_volatility="FAIL_CLOSED"),
            dict(corr=_bomb(), fail_mode_correlation="FAIL_CLOSED"),
            dict(expo=_bomb(), fail_mode_exposure="FAIL_CLOSED"),
        ]
        for kwargs in gates:
            with caplog.at_level(logging.ERROR):
                o, _ = _make(**kwargs)
                run(o.check(**BASE))
            assert len(caplog.records) > 0, f"No log for {list(kwargs.keys())}"
            caplog.clear()

    def test_fail_open_triggers_critical(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            o, _ = _make(equity=_bomb(), fail_mode_equity="FAIL_OPEN")
            run(o.check(**BASE))
        assert any(r.levelno >= logging.CRITICAL for r in caplog.records)


class TestBackwardCompatibility:
    def test_no_gates_all_approved(self):
        o, _ = _make()
        assert run(o.check(**BASE)).approved

    def test_invalid_sl_still_blocked_always(self):
        o, _ = _make()
        kw = dict(BASE); kw["stop_loss"] = kw["entry_price"]
        r = run(o.check(**kw))
        assert not r.approved
        assert r.block_reason == "INVALID_SL"

    def test_old_string_params_still_work(self):
        o, m = _make(fail_mode_correlation="FAIL_OPEN", fail_mode_exposure="FAIL_CLOSED")
        assert o._fail_corr == m.FailMode.FAIL_OPEN
        assert o._fail_exp  == m.FailMode.FAIL_CLOSED

    def test_exposure_engine_no_args_works(self):
        mod = _expo_mod()
        eng = mod.ExposureControlEngine()
        r = eng.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade

    def test_get_exposure_control_singleton(self):
        mod = _expo_mod()
        e1 = mod.get_exposure_control()
        e2 = mod.get_exposure_control()
        assert e1 is e2

    def test_default_risk_percent_still_respected(self):
        def _bomb_lot():
            m = MagicMock()
            m.calculate = MagicMock(side_effect=RuntimeError("lot bomb"))
            return m
        o, _ = _make(lot=_bomb_lot(), fail_mode_lot="FAIL_OPEN", default_risk_percent=3.0)
        r = run(o.check(**BASE))
        assert r.approved
        assert r.risk_percent == 3.0
