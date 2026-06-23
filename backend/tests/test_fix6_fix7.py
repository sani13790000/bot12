"""test_fix6_fix7.py - FIX #6 Fail-Closed Mode + FIX #7 Dead Code (46 tests)"""
from __future__ import annotations
import ast
import sys
import types
import logging
import importlib.util
import pathlib
from enum import Enum
from unittest.mock import MagicMock
import asyncio

BASE = pathlib.Path(__file__).parent.parent / "risk"

_fm_mod = types.ModuleType("backend.risk.fail_mode")

class FailMode(str, Enum):
    FAIL_CLOSED = "FAIL_CLOSED"
    FAIL_OPEN   = "FAIL_OPEN"

def _coerce(v) -> FailMode:
    if isinstance(v, FailMode): return v
    return FailMode(str(v).upper())

_fm_mod.FailMode = FailMode
_fm_mod.coerce   = _coerce
sys.modules["backend.risk.fail_mode"] = _fm_mod

def _load(name: str) -> types.ModuleType:
    path = BASE / f"{name}.py"
    src  = path.read_text()
    mod  = types.ModuleType(name)
    mod.__file__    = str(path)
    mod.__package__ = ""
    backend      = sys.modules.get("backend")      or types.ModuleType("backend")
    backend_risk = sys.modules.get("backend.risk") or types.ModuleType("backend.risk")
    pip_mod = sys.modules.get("backend.risk._pip_helpers") or types.ModuleType("backend.risk._pip_helpers")
    pip_mod._price_to_pips     = lambda sym, d: d * 10_000
    pip_mod._estimate_risk_pct = lambda sym, pd, lot, bal: (1.0, "estimated")
    sys.modules.setdefault("backend", backend)
    sys.modules.setdefault("backend.risk", backend_risk)
    sys.modules.setdefault("backend.risk._pip_helpers", pip_mod)
    sys.modules[name] = mod
    exec(compile(src, str(path), "exec"), mod.__dict__)
    return mod

_vf_mod   = _load("volatility_filter")
_ec_mod   = _load("exposure_control")
_cf_mod   = _load("correlation_filter")
_orch_mod = _load("risk_orchestrator")
_pr_mod   = _load("portfolio_risk")


class TestFix6_FailMode_Canonical:
    def test_fail_mode_values(self):
        assert FailMode.FAIL_CLOSED.value == "FAIL_CLOSED"
        assert FailMode.FAIL_OPEN.value   == "FAIL_OPEN"
    def test_coerce_from_string(self):
        assert _coerce("FAIL_CLOSED") is FailMode.FAIL_CLOSED
        assert _coerce("FAIL_OPEN")   is FailMode.FAIL_OPEN
        assert _coerce("fail_closed") is FailMode.FAIL_CLOSED
    def test_coerce_passthrough(self):
        assert _coerce(FailMode.FAIL_CLOSED) is FailMode.FAIL_CLOSED
    def test_all_modules_share_same_failmode(self):
        for mod in [_vf_mod, _ec_mod, _cf_mod, _orch_mod, _pr_mod]:
            assert mod.FailMode is FailMode, f"{mod.__name__}.FailMode not shared"
    def test_fail_closed_is_default_in_config(self):
        cfg = _vf_mod.VolatilityFilterConfig()
        assert cfg.fail_mode is FailMode.FAIL_CLOSED
    def test_fail_mode_enum_str_compat(self):
        assert FailMode.FAIL_CLOSED == "FAIL_CLOSED"
        assert FailMode.FAIL_OPEN   == "FAIL_OPEN"


class TestFix6_VolatilityFilter:
    def _vf(self, fm="FAIL_CLOSED"):
        cfg = _vf_mod.VolatilityFilterConfig(fail_mode=FailMode[fm])
        return _vf_mod.VolatilityFilter(config=cfg)
    def test_fail_mode_cached_in_init(self):
        vf = self._vf("FAIL_CLOSED")
        assert hasattr(vf, "_fail_mode")
        assert vf._fail_mode is FailMode.FAIL_CLOSED
    def test_fail_mode_open_cached(self):
        vf = self._vf("FAIL_OPEN")
        assert vf._fail_mode is FailMode.FAIL_OPEN
    def test_exception_fail_closed_blocks(self):
        vf = self._vf("FAIL_CLOSED")
        vf._check_inner = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        r = vf.check(0.001, [0.001], 0.0001, 0.0001, "EURUSD")
        assert r.can_trade is False
        assert "FAIL_CLOSED" in r.reason
    def test_exception_fail_open_allows(self):
        vf = self._vf("FAIL_OPEN")
        vf._check_inner = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom"))
        r = vf.check(0.001, [0.001], 0.0001, 0.0001, "EURUSD")
        assert r.can_trade is True
        assert "FAIL_OPEN" in r.reason
    def test_normal_operation_no_gate_error(self):
        vf = self._vf("FAIL_CLOSED")
        vf.update_atr(0.0001)
        r = vf.check(0.9999, [0.0001], 0.0001, 0.0001, "EURUSD")
        assert "GATE_ERROR" not in r.reason


class TestFix6_ExposureEngine:
    def _ec(self, fm="FAIL_CLOSED"):
        return _ec_mod.ExposureControlEngine(fail_mode=FailMode[fm])
    def test_default_fail_closed(self):
        ec = _ec_mod.ExposureControlEngine()
        assert ec._fail_mode is FailMode.FAIL_CLOSED
    def test_exception_fail_closed_blocks(self):
        ec = self._ec("FAIL_CLOSED")
        ec._check_inner = MagicMock(side_effect=ValueError("db error"))
        r = ec.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade is False
        assert "FAIL_CLOSED" in r.reason
    def test_exception_fail_open_allows(self):
        ec = self._ec("FAIL_OPEN")
        ec._check_inner = MagicMock(side_effect=ValueError("db error"))
        r = ec.check("EURUSD", "BUY", 1.0, [])
        assert r.can_trade is True
    def test_snapshot_exception_fail_closed(self):
        ec = self._ec("FAIL_CLOSED")
        ec._snapshot_inner = MagicMock(side_effect=RuntimeError("snap error"))
        snap = ec.get_snapshot([])
        assert snap.can_open_new is False
    def test_snapshot_exception_fail_open(self):
        ec = self._ec("FAIL_OPEN")
        ec._snapshot_inner = MagicMock(side_effect=RuntimeError("snap error"))
        snap = ec.get_snapshot([])
        assert snap.can_open_new is True
    def test_normal_check_no_exception(self):
        ec = self._ec("FAIL_CLOSED")
        r = ec.check("EURUSD", "BUY", 1.0, [])
        assert "GATE_ERROR" not in r.reason


class TestFix6_CorrelationFilter:
    def _cf(self, fm="FAIL_CLOSED"):
        cfg = _cf_mod.CorrelationFilterConfig(fail_mode=FailMode[fm])
        return _cf_mod.CorrelationFilter(config=cfg)
    def test_default_fail_closed(self):
        cf = _cf_mod.CorrelationFilter()
        assert cf._fail_mode is FailMode.FAIL_CLOSED
    def test_exception_fail_closed_blocks(self):
        cf = self._cf("FAIL_CLOSED")
        cf._check_inner = MagicMock(side_effect=RuntimeError("matrix singular"))
        r = asyncio.run(cf.check("EURUSD", "BUY", [], 1.0))
        assert r.can_trade is False
        assert "FAIL_CLOSED" in r.reason
    def test_exception_fail_open_allows(self):
        cf = self._cf("FAIL_OPEN")
        cf._check_inner = MagicMock(side_effect=RuntimeError("matrix singular"))
        r = asyncio.run(cf.check("EURUSD", "BUY", [], 1.0))
        assert r.can_trade is True
    def test_fail_mode_property(self):
        cf = self._cf("FAIL_OPEN")
        assert cf.fail_mode is FailMode.FAIL_OPEN


class TestFix6_Orchestrator:
    def test_all_6_gates_default_fail_closed(self):
        orch = _orch_mod.RiskOrchestrator()
        for attr in ["_fail_equity","_fail_daily","_fail_vol","_fail_corr","_fail_lot","_fail_exp"]:
            assert getattr(orch, attr) is FailMode.FAIL_CLOSED, f"{attr} not FAIL_CLOSED"
    def test_per_gate_override(self):
        orch = _orch_mod.RiskOrchestrator(fail_mode_equity="FAIL_OPEN", fail_mode_daily="FAIL_OPEN")
        assert orch._fail_equity is FailMode.FAIL_OPEN
        assert orch._fail_daily  is FailMode.FAIL_OPEN
        assert orch._fail_vol    is FailMode.FAIL_CLOSED
    def test_string_coerce_accepted(self):
        orch = _orch_mod.RiskOrchestrator(fail_mode_volatility="FAIL_OPEN")
        assert orch._fail_vol is FailMode.FAIL_OPEN
    def test_equity_gate_fail_closed_blocks(self):
        mock_eq = MagicMock()
        mock_eq.check = MagicMock(side_effect=RuntimeError("equity down"))
        orch = _orch_mod.RiskOrchestrator(equity_guard=mock_eq, fail_mode_equity="FAIL_CLOSED")
        result = asyncio.run(orch.check(
            user_id="u1", symbol="EURUSD", direction="BUY",
            entry_price=1.10, stop_loss=1.09, account_balance=10000,
        ))
        assert result.approved is False
    def test_equity_gate_fail_open_passes(self):
        mock_eq = MagicMock()
        mock_eq.check = MagicMock(side_effect=RuntimeError("equity down"))
        orch = _orch_mod.RiskOrchestrator(equity_guard=mock_eq, fail_mode_equity="FAIL_OPEN")
        result = asyncio.run(orch.check(
            user_id="u1", symbol="EURUSD", direction="BUY",
            entry_price=1.10, stop_loss=1.09, account_balance=10000,
        ))
        assert "EQUITY_FAIL_OPEN" in result.gates_passed
    def test_every_exception_logs_critical(self):
        src = (BASE / "risk_orchestrator.py").read_text()
        assert src.count("logger.critical") >= 6


class TestFix7_DeadImports:
    def test_risk_orchestrator_no_asyncio_import(self):
        src  = (BASE / "risk_orchestrator.py").read_text()
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names: imported.add(a.asname or a.name)
        assert "asyncio" not in imported, "dead asyncio still imported"
    def test_risk_orchestrator_no_asyncio_dot_usage(self):
        src = (BASE / "risk_orchestrator.py").read_text()
        assert "asyncio." not in src
    def test_volatility_filter_field_import_removed(self):
        src  = (BASE / "volatility_filter.py").read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "dataclasses":
                for alias in node.names:
                    name = alias.asname or alias.name
                    assert name != "field", "dead 'field' still imported"
    def test_volatility_filter_dataclass_still_imported(self):
        src = (BASE / "volatility_filter.py").read_text()
        assert "from dataclasses import dataclass" in src


class TestFix7_FailModeConsolidation:
    def test_portfolio_risk_imports_from_canonical(self):
        src = (BASE / "portfolio_risk.py").read_text()
        assert "from backend.risk.fail_mode import FailMode" in src
    def test_portfolio_risk_failmode_is_shared(self):
        assert _pr_mod.FailMode is FailMode
    def test_portfolio_risk_failmode_values(self):
        FM = _pr_mod.FailMode
        assert FM.FAIL_CLOSED.value == "FAIL_CLOSED"
        assert FM.FAIL_OPEN.value   == "FAIL_OPEN"
    def test_portfolio_risk_local_class_is_fallback_only(self):
        src   = (BASE / "portfolio_risk.py").read_text()
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "class FailMode" in line and "str, Enum" in line:
                region = "\n".join(lines[max(0, i-8):i+2])
                assert "NameError" in region or "except" in region, \
                    f"FailMode class at line {i+1} not guarded as fallback"


class TestFix7_FailModeCachedInVolatilityFilter:
    def test_source_uses_self_fail_mode_in_except(self):
        src = (BASE / "volatility_filter.py").read_text()
        assert "self._fail_mode is FailMode.FAIL_CLOSED" in src
    def test_no_getattr_in_except_block(self):
        src   = (BASE / "volatility_filter.py").read_text()
        lines = src.splitlines()
        in_except = False
        for i, line in enumerate(lines):
            if line.strip().startswith("except Exception as exc:") and i > 250:
                in_except = True
            if in_except and "getattr(self._cfg" in line and "fail_mode" in line:
                raise AssertionError(f"Line {i+1}: getattr still in except block")
            if in_except and line.strip().startswith("def ") and i > 280:
                break
    def test_fail_mode_cached_correctly_closed(self):
        cfg = _vf_mod.VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED)
        vf  = _vf_mod.VolatilityFilter(config=cfg)
        assert vf._fail_mode is FailMode.FAIL_CLOSED
    def test_fail_mode_cached_correctly_open(self):
        cfg = _vf_mod.VolatilityFilterConfig(fail_mode=FailMode.FAIL_OPEN)
        vf  = _vf_mod.VolatilityFilter(config=cfg)
        assert vf._fail_mode is FailMode.FAIL_OPEN
    def test_cache_not_affected_by_config_mutation(self):
        cfg = _vf_mod.VolatilityFilterConfig(fail_mode=FailMode.FAIL_CLOSED)
        vf  = _vf_mod.VolatilityFilter(config=cfg)
        cfg.fail_mode = FailMode.FAIL_OPEN
        assert vf._fail_mode is FailMode.FAIL_CLOSED


class TestFix7_NoUnusedLocks:
    def test_correlation_filter_lock_is_used(self):
        src = (BASE / "correlation_filter.py").read_text()
        assert "self._lock = asyncio.Lock()" in src
        assert "async with self._lock" in src
    def test_no_dead_locks_in_other_files(self):
        for name in ["volatility_filter", "exposure_control", "portfolio_risk"]:
            src = (BASE / f"{name}.py").read_text()
            if "asyncio.Lock()" in src:
                assert "async with" in src or "await" in src, \
                    f"{name}: asyncio.Lock() created but never used"


class TestFix6Fix7_Integration:
    def test_full_dead_code_audit(self):
        orch_src = (BASE / "risk_orchestrator.py").read_text()
        vf_src   = (BASE / "volatility_filter.py").read_text()
        pr_src   = (BASE / "portfolio_risk.py").read_text()
        checks = {
            "orch_no_asyncio_import":   "import asyncio\n" not in orch_src,
            "orch_no_asyncio_dot":      "asyncio." not in orch_src,
            "vf_no_dead_field_import":  "dataclass, field" not in vf_src,
            "vf_fail_mode_cached":      "self._fail_mode" in vf_src,
            "vf_except_uses_cached":    "self._fail_mode is FailMode" in vf_src,
            "pr_imports_canonical":     "from backend.risk.fail_mode import FailMode" in pr_src,
        }
        failed = [k for k, v in checks.items() if not v]
        assert not failed, f"Dead code audit failed: {failed}"
    def test_backward_compat_no_args_constructors(self):
        _vf_mod.VolatilityFilter()
        _ec_mod.ExposureControlEngine()
        _cf_mod.CorrelationFilter()
        _orch_mod.RiskOrchestrator()
    def test_backward_compat_check_signature_unchanged(self):
        import inspect
        ec  = _ec_mod.ExposureControlEngine()
        sig = inspect.signature(ec.check)
        params = list(sig.parameters)
        assert "new_symbol"       in params
        assert "new_direction"    in params
        assert "new_risk_percent" in params
        assert "open_positions"   in params
    def test_fail_mode_identity_across_all_modules(self):
        for mod in [_vf_mod, _ec_mod, _cf_mod, _orch_mod, _pr_mod]:
            assert mod.FailMode is FailMode, f"{mod.__name__}.FailMode is different object"
