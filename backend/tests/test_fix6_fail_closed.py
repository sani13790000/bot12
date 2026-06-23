"""backend/tests/test_fix6_fail_closed.py
FIX #6 - Fail-Closed Mode - 48 tests
All tests use production files.

Coverage:
  TestFailModeCanonical      8
  TestExposureFailMode      10
  TestCorrelationFailMode    8
  TestVolatilityFailMode     6
  TestOrchestratorGates     10
  TestLoggingAlways          4
  TestBackwardCompat         2

Total: 48 tests
"""
from __future__ import annotations

import asyncio
import logging
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Bootstrap: inject stubs BEFORE importing any production module
# ---------------------------------------------------------------------------

def _bootstrap():
    b  = types.ModuleType("backend")
    r  = types.ModuleType("backend.risk")
    b.risk = r
    sys.modules.setdefault("backend",      b)
    sys.modules.setdefault("backend.risk", r)
    ph = types.ModuleType("backend.risk._pip_helpers")
    ph._price_to_pips     = lambda sym, d: round(d * 10_000, 4)
    ph._estimate_risk_pct = lambda sym, pd, lot, bal: (1.0, "test")
    sys.modules.setdefault("backend.risk._pip_helpers", ph)
    r._pip_helpers = ph
    cl = types.ModuleType("backend.core")
    lg = types.ModuleType("backend.core.logger")
    lg.get_logger = logging.getLogger
    b.core = cl; cl.logger = lg
    sys.modules.setdefault("backend.core",        cl)
    sys.modules.setdefault("backend.core.logger", lg)
    return b, r


_bootstrap()

import importlib.util as _ilu
import pathlib

_BASE = pathlib.Path(__file__).parent.parent / "risk"


def _load(name: str, rel: str):
    path = _BASE / rel
    spec = _ilu.spec_from_file_location(name, path)
    mod  = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_fm   = _load("backend.risk.fail_mode",          "fail_mode.py")
_ec   = _load("backend.risk.exposure_control",   "exposure_control.py")
_cf   = _load("backend.risk.correlation_filter", "correlation_filter.py")
_vf   = _load("backend.risk.volatility_filter",  "volatility_filter.py")
_orch = _load("backend.risk.risk_orchestrator",  "risk_orchestrator.py")

FailMode               = _fm.FailMode
coerce                 = _fm.coerce
ExposureControlEngine  = _ec.ExposureControlEngine
ExposurePosition       = _ec.ExposurePosition
CorrelationFilter      = _cf.CorrelationFilter
CorrelationFilterConfig= _cf.CorrelationFilterConfig
RiskOrchestrator       = _orch.RiskOrchestrator


def run(coro):
    return asyncio.run(coro)


def _bomb_sync(exc=RuntimeError, msg="boom"):
    m = MagicMock()
    m.check.side_effect = exc(msg)
    return m


def _bomb_async(exc=RuntimeError, msg="boom"):
    m = MagicMock()
    m.check = AsyncMock(side_effect=exc(msg))
    m.calculate = AsyncMock(side_effect=exc(msg))
    return m


def _ok_sync():
    m = MagicMock()
    r = MagicMock()
    r.can_trade = True
    r.reason = ""
    r.lot_multiplier = 1.0
    m.check.return_value = r
    return m


BASE = dict(
    symbol="EURUSD", direction="BUY",
    entry_price=1.1000, stop_loss=1.0950,
    account_balance=10_000.0,
    user_id="u1", signal_id="s1",
)


# ===========================================================================
# TestFailModeCanonical
# ===========================================================================

class TestFailModeCanonical:
    def test_enum_values(self):
        assert FailMode.FAIL_CLOSED == "FAIL_CLOSED"
        assert FailMode.FAIL_OPEN   == "FAIL_OPEN"

    def test_coerce_string_closed(self):
        assert coerce("FAIL_CLOSED") is FailMode.FAIL_CLOSED

    def test_coerce_string_open(self):
        assert coerce("FAIL_OPEN") is FailMode.FAIL_OPEN

    def test_coerce_lowercase(self):
        assert coerce("fail_closed") is FailMode.FAIL_CLOSED
        assert coerce("fail_open")   is FailMode.FAIL_OPEN

    def test_coerce_enum_passthrough(self):
        assert coerce(FailMode.FAIL_CLOSED) is FailMode.FAIL_CLOSED

    def test_coerce_invalid_raises(self):
        with pytest.raises(ValueError):
            coerce("BANANA")

    def test_all_modules_same_enum(self):
        assert _ec.FailMode   is _fm.FailMode
        assert _cf.FailMode   is _fm.FailMode
        assert _vf.FailMode   is _fm.FailMode
        assert _orch.FailMode is _fm.FailMode

    def test_fail_mode_is_str_subclass(self):
        assert issubclass(FailMode, str)
        assert FailMode.FAIL_CLOSED == "FAIL_CLOSED"


# ===========================================================================
# TestExposureFailMode
# ===========================================================================

class TestExposureFailMode:
    def test_default_is_fail_closed(self):
        e = ExposureControlEngine()
        assert e._fail_mode is FailMode.FAIL_CLOSED

    def test_string_fail_open_accepted(self):
        e = ExposureControlEngine(fail_mode="FAIL_OPEN")
        assert e._fail_mode is FailMode.FAIL_OPEN

    def test_enum_fail_open_accepted(self):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        assert e._fail_mode is FailMode.FAIL_OPEN

    def test_check_inner_exception_fail_closed_blocks(self):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        e._check_inner = MagicMock(side_effect=RuntimeError("inner"))
        r = e.check("EURUSD", "BUY", 1.0, [])
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_check_inner_exception_fail_open_allows(self):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        e._check_inner = MagicMock(side_effect=RuntimeError("inner"))
        r = e.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade
        assert r.reason == "FAIL_OPEN_EXCEPTION_IGNORED"

    def test_snapshot_exception_fail_closed_blocks(self):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        e._snapshot_inner = MagicMock(side_effect=RuntimeError("snap"))
        s = e.get_snapshot([])
        assert not s.can_open_new
        assert "FAIL_CLOSED" in s.block_reason

    def test_snapshot_exception_fail_open_allows(self):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        e._snapshot_inner = MagicMock(side_effect=RuntimeError("snap"))
        assert e.get_snapshot([]).can_open_new

    def test_normal_operation_unaffected(self):
        e = ExposureControlEngine()
        r = e.check("GBPUSD", "BUY", 1.0, [])
        assert r.can_trade

    def test_exception_always_logged(self, caplog):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        e._check_inner = MagicMock(side_effect=RuntimeError("log_me"))
        with caplog.at_level(logging.ERROR, logger="risk.exposure"):
            e.check("EURUSD", "BUY", 1.0, [])
        assert any("log_me" in r.message or "log_me" in str(r.exc_info)
                   for r in caplog.records)

    def test_fail_open_critical_logged(self, caplog):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_OPEN)
        e._check_inner = MagicMock(side_effect=RuntimeError("crit"))
        with caplog.at_level(logging.CRITICAL, logger="risk.exposure"):
            e.check("EURUSD", "BUY", 1.0, [])
        assert any(r.levelno >= logging.CRITICAL for r in caplog.records)


# ===========================================================================
# TestCorrelationFailMode
# ===========================================================================

class TestCorrelationFailMode:
    def test_default_is_fail_closed(self):
        c = CorrelationFilter()
        assert c.fail_mode is FailMode.FAIL_CLOSED

    def test_string_fail_open(self):
        c = CorrelationFilter(fail_mode="FAIL_OPEN")
        assert c.fail_mode is FailMode.FAIL_OPEN

    def test_config_fail_mode_respected(self):
        cfg = CorrelationFilterConfig(fail_mode=FailMode.FAIL_OPEN)
        c   = CorrelationFilter(config=cfg)
        assert c.fail_mode is FailMode.FAIL_OPEN

    def test_init_kwarg_overrides_config(self):
        cfg = CorrelationFilterConfig(fail_mode=FailMode.FAIL_OPEN)
        c   = CorrelationFilter(config=cfg, fail_mode=FailMode.FAIL_CLOSED)
        assert c.fail_mode is FailMode.FAIL_CLOSED

    def test_check_exception_fail_closed_blocks(self):
        c = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        c._check_inner = AsyncMock(side_effect=RuntimeError("corr"))
        r = run(c.check("EURUSD", "BUY", [], 1.0))
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_check_exception_fail_open_allows(self):
        c = CorrelationFilter(fail_mode=FailMode.FAIL_OPEN)
        c._check_inner = AsyncMock(side_effect=RuntimeError("corr"))
        r = run(c.check("EURUSD", "BUY", [], 1.0))
        assert r.can_trade
        assert "FAIL_OPEN" in r.reason

    def test_exception_always_logged(self, caplog):
        c = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        c._check_inner = AsyncMock(side_effect=RuntimeError("log_corr"))
        with caplog.at_level(logging.CRITICAL, logger="risk.correlation_filter"):
            run(c.check("EURUSD", "BUY", [], 1.0))
        assert len(caplog.records) > 0

    def test_normal_empty_positions_passes(self):
        c = CorrelationFilter()
        r = run(c.check("EURUSD", "BUY", [], 1.0))
        assert r.can_trade


# ===========================================================================
# TestVolatilityFailMode
# ===========================================================================

class TestVolatilityFailMode:
    _CALL = dict(current_atr=1.0, atr_history=[1.0]*14,
                 current_spread=0.0002, avg_spread=0.0002, symbol="EURUSD")

    def _filter(self, fail_mode=FailMode.FAIL_CLOSED):
        cfg = _vf.VolatilityFilterConfig(fail_mode=fail_mode)
        return _vf.VolatilityFilter(cfg)

    def test_default_config_is_fail_closed(self):
        cfg = _vf.VolatilityFilterConfig()
        assert cfg.fail_mode is FailMode.FAIL_CLOSED

    def test_check_exception_fail_closed_blocks(self):
        vf = self._filter(FailMode.FAIL_CLOSED)
        vf._check_inner = MagicMock(side_effect=RuntimeError("vol"))
        r = vf.check(**self._CALL)
        assert not r.can_trade
        assert "FAIL_CLOSED" in r.reason

    def test_check_exception_fail_open_allows(self):
        vf = self._filter(FailMode.FAIL_OPEN)
        vf._check_inner = MagicMock(side_effect=RuntimeError("vol"))
        r = vf.check(**self._CALL)
        assert r.can_trade

    def test_fail_open_reason_contains_marker(self):
        vf = self._filter(FailMode.FAIL_OPEN)
        vf._check_inner = MagicMock(side_effect=RuntimeError("vol"))
        r = vf.check(**self._CALL)
        assert "FAIL_OPEN" in r.reason

    def test_exception_logged(self, caplog):
        vf = self._filter(FailMode.FAIL_CLOSED)
        vf._check_inner = MagicMock(side_effect=RuntimeError("log_vol"))
        with caplog.at_level(logging.ERROR, logger="risk.volatility_filter"):
            vf.check(**self._CALL)
        assert len(caplog.records) > 0

    def test_normal_operation_unaffected(self):
        vf = self._filter()
        r = vf.check(**self._CALL)
        assert isinstance(r.can_trade, bool)


# ===========================================================================
# TestOrchestratorGates
# ===========================================================================

class TestOrchestratorGates:
    def test_all_defaults_fail_closed(self):
        o = RiskOrchestrator()
        FC = FailMode.FAIL_CLOSED
        assert all(x is FC for x in [
            o._fail_equity, o._fail_daily, o._fail_vol,
            o._fail_corr, o._fail_lot, o._fail_exp,
        ])

    def test_equity_fail_closed_blocks(self):
        o = RiskOrchestrator(equity_guard=_bomb_sync(), fail_mode_equity="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "EQUITY_GATE_ERROR" in r.block_reason

    def test_equity_fail_open_allows(self):
        o = RiskOrchestrator(equity_guard=_bomb_sync(), fail_mode_equity="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved
        assert "EQUITY_FAIL_OPEN" in r.gates_passed

    def test_daily_fail_closed_blocks(self):
        o = RiskOrchestrator(daily_limits=_bomb_sync(), fail_mode_daily="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "DAILY_LIMITS_GATE_ERROR" in r.block_reason

    def test_daily_fail_open_allows(self):
        o = RiskOrchestrator(daily_limits=_bomb_sync(), fail_mode_daily="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved

    def test_volatility_fail_closed_blocks(self):
        o = RiskOrchestrator(volatility_filter=_bomb_sync(), fail_mode_volatility="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "VOLATILITY_GATE_ERROR" in r.block_reason

    def test_volatility_fail_open_allows(self):
        o = RiskOrchestrator(volatility_filter=_bomb_sync(), fail_mode_volatility="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved

    def test_correlation_fail_closed_blocks(self):
        o = RiskOrchestrator(correlation_filter=_bomb_sync(), fail_mode_correlation="FAIL_CLOSED")
        r = run(o.check(**BASE))
        assert not r.approved
        assert "CORRELATION_GATE_ERROR" in r.block_reason

    def test_correlation_fail_open_allows(self):
        o = RiskOrchestrator(correlation_filter=_bomb_sync(), fail_mode_correlation="FAIL_OPEN")
        r = run(o.check(**BASE))
        assert r.approved

    def test_gates_independent(self):
        o = RiskOrchestrator(
            correlation_filter=_bomb_sync(), fail_mode_correlation="FAIL_OPEN",
            equity_guard=_bomb_sync(),        fail_mode_equity="FAIL_CLOSED",
        )
        r = run(o.check(**BASE))
        assert not r.approved
        assert "EQUITY_GATE_ERROR" in r.block_reason


# ===========================================================================
# TestLoggingAlways
# ===========================================================================

class TestLoggingAlways:
    def test_equity_exception_logged(self, caplog):
        with caplog.at_level(logging.ERROR):
            o = RiskOrchestrator(equity_guard=_bomb_sync(), fail_mode_equity="FAIL_CLOSED")
            run(o.check(**BASE))
        assert len(caplog.records) > 0

    def test_fail_open_logs_critical(self, caplog):
        with caplog.at_level(logging.CRITICAL):
            o = RiskOrchestrator(equity_guard=_bomb_sync(), fail_mode_equity="FAIL_OPEN")
            run(o.check(**BASE))
        assert any(r.levelno >= logging.CRITICAL for r in caplog.records)

    def test_exposure_engine_exception_logged(self, caplog):
        e = ExposureControlEngine(fail_mode=FailMode.FAIL_CLOSED)
        e._check_inner = MagicMock(side_effect=RuntimeError("xlog"))
        with caplog.at_level(logging.ERROR):
            e.check("EURUSD", "BUY", 1.0, [])
        assert len(caplog.records) > 0

    def test_correlation_exception_logged(self, caplog):
        c = CorrelationFilter(fail_mode=FailMode.FAIL_CLOSED)
        c._check_inner = AsyncMock(side_effect=RuntimeError("clog"))
        with caplog.at_level(logging.CRITICAL):
            run(c.check("EURUSD", "BUY", [], 1.0))
        assert len(caplog.records) > 0


# ===========================================================================
# TestBackwardCompat
# ===========================================================================

class TestBackwardCompat:
    def test_orchestrator_no_args_approved(self):
        o = RiskOrchestrator()
        r = run(o.check(**BASE))
        assert r.approved

    def test_exposure_engine_no_args(self):
        e = ExposureControlEngine()
        r = e.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade
