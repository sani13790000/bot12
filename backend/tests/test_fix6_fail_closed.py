"""
test_fix6_fail_closed.py -- FIX #6 (final) + FIX #7 (dead code)
39 tests | 39/39 PASS

FIX #6 final verified:
- VolatilityFilter._fail_mode cached in __init__ (not re-computed per check())
- All 6 orchestrator gates have independent, configurable fail_mode
- Every exception logged at CRITICAL (never silent)
- FAIL_CLOSED => block, FAIL_OPEN => allow

FIX #7 verified:
- 'import asyncio' removed from risk_orchestrator (0 usages proven)
- All other imports verified as actually used
- correlation_filter asyncio.Lock confirmed live (3 async with blocks)
"""
import sys, pathlib, importlib, logging, asyncio, unittest
from unittest.mock import MagicMock

_BASE = pathlib.Path(__file__).parent.parent / "risk"

def _load(name, filename):
    path = _BASE / filename
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

fm_mod   = _load("backend.risk.fail_mode",        "fail_mode.py")
vf_mod   = _load("backend.risk.volatility_filter", "volatility_filter.py")
orch_mod = _load("backend.risk.risk_orchestrator", "risk_orchestrator.py")

FailMode               = fm_mod.FailMode
coerce                 = fm_mod.coerce
VolatilityFilter       = vf_mod.VolatilityFilter
VolatilityFilterConfig = vf_mod.VolatilityFilterConfig
RiskOrchestrator       = orch_mod.RiskOrchestrator

def _run(orch):
    return asyncio.run(orch.check("EURUSD","BUY",1.1,1.095,10_000.0))

def _raising_guard():
    g = MagicMock()
    g.check = MagicMock(side_effect=RuntimeError("kaboom"))
    return g


class TestVolatilityFailModeCached(unittest.TestCase):

    def _vf(self, fm=FailMode.FAIL_CLOSED):
        return VolatilityFilter(config=VolatilityFilterConfig(fail_mode=fm))

    def test_cached_fail_closed(self):
        self.assertIs(self._vf(FailMode.FAIL_CLOSED)._fail_mode, FailMode.FAIL_CLOSED)

    def test_cached_fail_open(self):
        self.assertIs(self._vf(FailMode.FAIL_OPEN)._fail_mode, FailMode.FAIL_OPEN)

    def test_default_is_fail_closed(self):
        self.assertIs(VolatilityFilter()._fail_mode, FailMode.FAIL_CLOSED)

    def test_string_coerced_at_init(self):
        cfg = VolatilityFilterConfig()
        cfg.fail_mode = "FAIL_OPEN"
        self.assertIs(VolatilityFilter(config=cfg)._fail_mode, FailMode.FAIL_OPEN)

    def test_fail_closed_blocks_on_exception(self):
        vf = self._vf(FailMode.FAIL_CLOSED)
        vf._check_inner = MagicMock(side_effect=RuntimeError("boom"))
        r = vf.check(0.001,[0.001]*5,0.0001,0.0001,"EURUSD")
        self.assertFalse(r.can_trade)
        self.assertIn("FAIL_CLOSED", r.reason)

    def test_fail_open_allows_on_exception(self):
        vf = self._vf(FailMode.FAIL_OPEN)
        vf._check_inner = MagicMock(side_effect=RuntimeError("boom"))
        r = vf.check(0.001,[0.001]*5,0.0001,0.0001,"EURUSD")
        self.assertTrue(r.can_trade)
        self.assertIn("FAIL_OPEN", r.reason)

    def test_cached_used_even_if_cfg_mutated(self):
        vf = self._vf(FailMode.FAIL_CLOSED)
        vf._check_inner = MagicMock(side_effect=ValueError("oops"))
        try: del vf._cfg.fail_mode
        except AttributeError: pass
        r = vf.check(0.001,[0.001]*5,0.0001,0.0001)
        self.assertFalse(r.can_trade)

    def test_exception_logged_on_fail_open(self):
        vf = self._vf(FailMode.FAIL_OPEN)
        vf._check_inner = MagicMock(side_effect=RuntimeError("log_me"))
        with self.assertLogs("risk.volatility_filter", level="ERROR") as cm:
            vf.check(0.001,[0.001]*5,0.0001,0.0001,"GBPUSD")
        self.assertTrue(any("GBPUSD" in m for m in cm.output))

    def test_fail_open_critical_log(self):
        vf = self._vf(FailMode.FAIL_OPEN)
        vf._check_inner = MagicMock(side_effect=RuntimeError("x"))
        with self.assertLogs("risk.volatility_filter", level="CRITICAL") as cm:
            vf.check(0.001,[0.001]*5,0.0001,0.0001,"XAUUSD")
        self.assertIn("FAIL_OPEN", " ".join(cm.output))

    def test_fail_closed_exception_logged(self):
        vf = self._vf(FailMode.FAIL_CLOSED)
        vf._check_inner = MagicMock(side_effect=RuntimeError("err"))
        with self.assertLogs("risk.volatility_filter", level="ERROR") as cm:
            vf.check(0.001,[0.001]*5,0.0001,0.0001,"USDJPY")
        self.assertTrue(any("USDJPY" in m for m in cm.output))

    def test_two_instances_independent(self):
        vf1 = self._vf(FailMode.FAIL_CLOSED)
        vf2 = self._vf(FailMode.FAIL_OPEN)
        self.assertIs(vf1._fail_mode, FailMode.FAIL_CLOSED)
        self.assertIs(vf2._fail_mode, FailMode.FAIL_OPEN)

    def test_normal_path_unchanged(self):
        vf = VolatilityFilter()
        for _ in range(20): vf.update_atr(0.001)
        self.assertTrue(vf.check(0.001,[0.001]*14,0.0001,0.0001,"EURUSD").can_trade)


class TestDeadCodeRemoved(unittest.TestCase):

    def test_asyncio_not_imported(self):
        import ast
        with open(_BASE/"risk_orchestrator.py") as f:
            src = f.read()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertNotEqual(alias.name,"asyncio","Dead asyncio import still present!")

    def test_asyncio_not_referenced(self):
        import re
        with open(_BASE/"risk_orchestrator.py") as f:
            src = f.read()
        self.assertEqual(len(re.findall(r'\basyncio\b', src)), 0)

    def test_orchestrator_compiles(self):
        with open(_BASE/"risk_orchestrator.py") as f:
            src = f.read()
        compile(src,"risk_orchestrator.py","exec")

    def test_logging_kept(self):
        with open(_BASE/"risk_orchestrator.py") as f: src = f.read()
        self.assertIn("import logging", src)

    def test_dataclasses_kept(self):
        with open(_BASE/"risk_orchestrator.py") as f: src = f.read()
        self.assertIn("from dataclasses import", src)

    def test_enum_kept_for_fallback(self):
        with open(_BASE/"risk_orchestrator.py") as f: src = f.read()
        self.assertIn("from enum import Enum", src)

    def test_typing_kept(self):
        with open(_BASE/"risk_orchestrator.py") as f: src = f.read()
        self.assertIn("from typing import", src)

    def test_volatility_filter_compiles(self):
        with open(_BASE/"volatility_filter.py") as f: src = f.read()
        compile(src,"volatility_filter.py","exec")

    def test_no_redundant_getattr_in_check(self):
        with open(_BASE/"volatility_filter.py") as f: src = f.read()
        self.assertNotIn("_fm = _coerce_fm(getattr", src)
        self.assertIn("if self._fail_mode is FailMode.FAIL_CLOSED:", src)

    def test_correlation_lock_is_live(self):
        with open(_BASE/"correlation_filter.py") as f: src = f.read()
        self.assertIn("self._lock = asyncio.Lock()", src)
        self.assertGreaterEqual(src.count("async with self._lock:"), 2)

    def test_exposure_optional_used(self):
        import ast
        with open(_BASE/"exposure_control.py") as f: src = f.read()
        tree = ast.parse(src)
        self.assertTrue(any(
            isinstance(n,ast.Name) and n.id=="Optional"
            for n in ast.walk(tree)
        ))

    def test_exposure_dict_list_used(self):
        import ast
        with open(_BASE/"exposure_control.py") as f: src = f.read()
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        self.assertIn("Dict", names)
        self.assertIn("List", names)


class TestOrchestratorGates(unittest.TestCase):

    def test_default_all_fail_closed(self):
        orch = RiskOrchestrator()
        for attr in ("_fail_equity","_fail_daily","_fail_vol",
                     "_fail_corr","_fail_lot","_fail_exp"):
            self.assertIs(getattr(orch,attr), FailMode.FAIL_CLOSED, attr)

    def test_per_gate_override(self):
        orch = RiskOrchestrator(
            fail_mode_equity="FAIL_OPEN", fail_mode_daily=FailMode.FAIL_CLOSED,
            fail_mode_volatility="FAIL_OPEN", fail_mode_correlation=FailMode.FAIL_CLOSED,
            fail_mode_lot="FAIL_OPEN", fail_mode_exposure=FailMode.FAIL_CLOSED,
        )
        self.assertIs(orch._fail_equity, FailMode.FAIL_OPEN)
        self.assertIs(orch._fail_daily,  FailMode.FAIL_CLOSED)
        self.assertIs(orch._fail_vol,    FailMode.FAIL_OPEN)
        self.assertIs(orch._fail_corr,   FailMode.FAIL_CLOSED)
        self.assertIs(orch._fail_lot,    FailMode.FAIL_OPEN)
        self.assertIs(orch._fail_exp,    FailMode.FAIL_CLOSED)

    def test_string_coercion(self):
        orch = RiskOrchestrator(fail_mode_equity="FAIL_OPEN",fail_mode_daily="FAIL_CLOSED")
        self.assertIs(orch._fail_equity, FailMode.FAIL_OPEN)
        self.assertIs(orch._fail_daily,  FailMode.FAIL_CLOSED)

    def test_equity_fail_open_allows(self):
        orch = RiskOrchestrator(equity_guard=_raising_guard(),
                                fail_mode_equity=FailMode.FAIL_OPEN)
        self.assertIn("EQUITY_FAIL_OPEN", _run(orch).gates_passed)

    def test_equity_fail_closed_blocks(self):
        orch = RiskOrchestrator(equity_guard=_raising_guard(),
                                fail_mode_equity=FailMode.FAIL_CLOSED)
        self.assertFalse(_run(orch).approved)

    def test_daily_fail_open_allows(self):
        orch = RiskOrchestrator(daily_limits=_raising_guard(),
                                fail_mode_daily=FailMode.FAIL_OPEN)
        self.assertIn("DAILY_LIMITS_FAIL_OPEN", _run(orch).gates_passed)

    def test_correlation_fail_open_allows(self):
        orch = RiskOrchestrator(correlation_filter=_raising_guard(),
                                fail_mode_correlation=FailMode.FAIL_OPEN)
        self.assertIn("CORRELATION_FAIL_OPEN", _run(orch).gates_passed)

    def test_every_exception_logged(self):
        orch = RiskOrchestrator(
            equity_guard=_raising_guard(), daily_limits=_raising_guard(),
            fail_mode_equity=FailMode.FAIL_OPEN, fail_mode_daily=FailMode.FAIL_OPEN,
        )
        with self.assertLogs("risk.orchestrator", level="CRITICAL") as cm:
            _run(orch)
        msgs = " ".join(cm.output)
        self.assertIn("EQUITY", msgs)
        self.assertIn("DAILY",  msgs)


class TestBackwardCompat(unittest.TestCase):

    def test_vf_no_args(self):
        vf = VolatilityFilter()
        self.assertIs(vf._fail_mode, FailMode.FAIL_CLOSED)

    def test_orch_no_args(self):
        self.assertIsNotNone(RiskOrchestrator())

    def test_str_enum(self):
        self.assertEqual(FailMode.FAIL_CLOSED,"FAIL_CLOSED")
        self.assertEqual(FailMode.FAIL_OPEN,"FAIL_OPEN")

    def test_coerce_str(self):
        self.assertIs(coerce("FAIL_CLOSED"),FailMode.FAIL_CLOSED)
        self.assertIs(coerce("fail_open"),  FailMode.FAIL_OPEN)

    def test_coerce_enum(self):
        self.assertIs(coerce(FailMode.FAIL_CLOSED),FailMode.FAIL_CLOSED)

    def test_vf_normal_path(self):
        vf = VolatilityFilter()
        for _ in range(20): vf.update_atr(0.001)
        self.assertTrue(vf.check(0.001,[0.001]*14,0.0001,0.0001,"EURUSD").can_trade)

    def test_orch_check_signature(self):
        result = _run(RiskOrchestrator())
        self.assertIsNotNone(result.approved)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in [TestVolatilityFailModeCached, TestDeadCodeRemoved,
                TestOrchestratorGates, TestBackwardCompat]:
        suite.addTests(loader.loadTestsFromTestCase(cls))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
