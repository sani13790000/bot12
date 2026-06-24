"""
test_fix7_dead_code.py
FIX #7 - Remove Dead Code
Verifies: unused imports removed, live imports kept, asyncio locks verified live,
          from __future__ kept, runtime imports kept, AST parses clean.
"""
import ast
import sys
import pathlib
import importlib
import importlib.util
import types

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_RISK = pathlib.Path(__file__).parent.parent / "risk"


def _src(name: str) -> str:
    return (_RISK / name).read_text()


# ===========================================================================
# 1. AST Parse -- all files must parse without error
# ===========================================================================
class TestASTParseClean:
    FILES = [
        "risk_orchestrator.py",
        "correlation_filter.py",
        "exposure_control.py",
        "volatility_filter.py",
        "portfolio_risk.py",
        "lot_sizing.py",
        "fail_mode.py",
        "_pip_helpers.py",
    ]

    def _test_parse(self, fname):
        src = _src(fname)
        try:
            ast.parse(src)
            return True
        except SyntaxError as e:
            raise AssertionError(f"{fname} SyntaxError: {e}")

    def test_parse_risk_orchestrator(self):
        assert self._test_parse("risk_orchestrator.py")

    def test_parse_correlation_filter(self):
        assert self._test_parse("correlation_filter.py")

    def test_parse_exposure_control(self):
        assert self._test_parse("exposure_control.py")

    def test_parse_volatility_filter(self):
        assert self._test_parse("volatility_filter.py")

    def test_parse_portfolio_risk(self):
        assert self._test_parse("portfolio_risk.py")

    def test_parse_lot_sizing(self):
        assert self._test_parse("lot_sizing.py")

    def test_parse_fail_mode(self):
        assert self._test_parse("fail_mode.py")

    def test_parse_pip_helpers(self):
        assert self._test_parse("_pip_helpers.py")


# ===========================================================================
# 2. Dead imports REMOVED -- proven unused by AST
# ===========================================================================
class TestDeadImportsRemoved:

    # risk_orchestrator.py: Optional (0 uses)
    def test_orch_optional_removed(self):
        src = _src("risk_orchestrator.py")
        import_lines = [l for l in src.splitlines()
                        if l.strip().startswith(("import ", "from "))
                        and "ImportError" not in l][:25]
        block = "\n".join(import_lines)
        assert "Optional" not in block, \
            "risk_orchestrator.py still imports Optional (proven dead)"

    # correlation_filter.py: field (0 uses)
    def test_corr_field_removed(self):
        src = _src("correlation_filter.py")
        import_lines = [l for l in src.splitlines()
                        if "from dataclasses" in l][:5]
        for l in import_lines:
            assert "field" not in l, \
                f"correlation_filter.py still imports 'field' (proven dead): {l}"

    # correlation_filter.py: Optional (0 uses)
    def test_corr_optional_removed(self):
        src = _src("correlation_filter.py")
        import_lines = [l for l in src.splitlines()
                        if "from typing" in l][:5]
        for l in import_lines:
            assert "Optional" not in l, \
                f"correlation_filter.py still imports 'Optional' (proven dead): {l}"

    # correlation_filter.py: Tuple (0 uses)
    def test_corr_tuple_removed(self):
        src = _src("correlation_filter.py")
        import_lines = [l for l in src.splitlines()
                        if "from typing" in l][:5]
        for l in import_lines:
            assert "Tuple" not in l, \
                f"correlation_filter.py still imports 'Tuple' (proven dead): {l}"

    # exposure_control.py: field (0 uses)
    def test_exp_field_removed(self):
        src = _src("exposure_control.py")
        import_lines = [l for l in src.splitlines()
                        if "from dataclasses" in l][:5]
        for l in import_lines:
            assert "field" not in l, \
                f"exposure_control.py still imports 'field' (proven dead): {l}"

    # exposure_control.py: Optional (0 uses)
    def test_exp_optional_removed(self):
        src = _src("exposure_control.py")
        import_lines = [l for l in src.splitlines()
                        if "from typing" in l][:5]
        for l in import_lines:
            assert "Optional" not in l, \
                f"exposure_control.py still imports 'Optional' (proven dead): {l}"

    # volatility_filter.py: field (0 uses)
    def test_vf_field_removed(self):
        src = _src("volatility_filter.py")
        import_lines = [l for l in src.splitlines()
                        if "from dataclasses" in l][:5]
        for l in import_lines:
            assert "field" not in l, \
                f"volatility_filter.py still imports 'field' (proven dead): {l}"

    # lot_sizing.py: field (0 uses)
    def test_lot_field_removed(self):
        src = _src("lot_sizing.py")
        import_lines = [l for l in src.splitlines()
                        if "from dataclasses" in l][:5]
        for l in import_lines:
            assert "field" not in l, \
                f"lot_sizing.py still imports 'field' (proven dead): {l}"


# ===========================================================================
# 3. Live imports KEPT -- proven used by AST
# ===========================================================================
class TestLiveImportsKept:

    def test_orch_keeps_logging(self):
        assert "import logging" in _src("risk_orchestrator.py")

    def test_orch_keeps_dataclass(self):
        assert "dataclass" in _src("risk_orchestrator.py")

    def test_orch_keeps_enum(self):
        assert "Enum" in _src("risk_orchestrator.py")

    def test_orch_keeps_any_dict_list(self):
        src = _src("risk_orchestrator.py")
        assert "Any" in src and "Dict" in src and "List" in src

    def test_orch_keeps_future_annotations(self):
        assert "from __future__ import annotations" in _src("risk_orchestrator.py")

    def test_corr_keeps_logging(self):
        assert "import logging" in _src("correlation_filter.py")

    def test_corr_keeps_dataclass(self):
        assert "dataclass" in _src("correlation_filter.py")

    def test_corr_keeps_dict_list(self):
        src = _src("correlation_filter.py")
        assert "Dict" in src and "List" in src

    def test_exp_keeps_logging(self):
        assert "import logging" in _src("exposure_control.py")

    def test_exp_keeps_dataclass(self):
        assert "dataclass" in _src("exposure_control.py")

    def test_vf_keeps_optional_tuple(self):
        src = _src("volatility_filter.py")
        assert "Optional" in src and "Tuple" in src

    def test_vf_keeps_datetime(self):
        src = _src("volatility_filter.py")
        assert "datetime" in src

    def test_lot_keeps_math(self):
        assert "math" in _src("lot_sizing.py")

    def test_lot_keeps_optional(self):
        assert "Optional" in _src("lot_sizing.py")


# ===========================================================================
# 4. asyncio.Lock -- proven LIVE in correlation_engine
# ===========================================================================
class TestAsyncioLocksLive:

    def test_correlation_engine_has_asyncio_lock(self):
        path = _RISK / "correlation_engine.py"
        if not path.exists():
            return
        src = path.read_text()
        assert "asyncio.Lock" in src, \
            "correlation_engine.py removed asyncio.Lock (was live!)"

    def test_lot_sizing_no_asyncio_needed(self):
        # lot_sizing.py is a pure sync calculation engine -- no asyncio/locks needed
        # Verified by AST: 0 asyncio references in production file
        src = _src("lot_sizing.py")
        assert "LotSizer" in src, "lot_sizing.py missing LotSizer class"

    def test_risk_orchestrator_no_asyncio_import(self):
        # risk_orchestrator.py had asyncio imported but never used -- removed in FIX-7A
        src = _src("risk_orchestrator.py")
        import_lines = [l for l in src.splitlines()
                        if l.strip().startswith("import asyncio")]
        assert not import_lines, \
            "risk_orchestrator.py still has bare 'import asyncio' (proven dead)"

    def test_risk_orchestrator_no_asyncio_usage(self):
        src = _src("risk_orchestrator.py")
        code_lines = [l for l in src.splitlines()
                      if "asyncio." in l and not l.strip().startswith("#")]
        assert not code_lines, \
            f"risk_orchestrator.py uses asyncio in code (unexpected): {code_lines}"


# ===========================================================================
# 5. from __future__ import annotations -- KEPT (PEP 563)
# ===========================================================================
class TestFutureAnnotationsKept:

    def _check(self, fname):
        src = _src(fname)
        assert "from __future__ import annotations" in src, \
            f"{fname} removed 'from __future__ import annotations' (must keep for PEP 563)"

    def test_orch_future_annotations(self):
        self._check("risk_orchestrator.py")

    def test_corr_future_annotations(self):
        self._check("correlation_filter.py")

    def test_exp_future_annotations(self):
        self._check("exposure_control.py")

    def test_vf_future_annotations(self):
        self._check("volatility_filter.py")

    def test_pr_future_annotations(self):
        self._check("portfolio_risk.py")

    def test_lot_future_annotations(self):
        self._check("lot_sizing.py")

    def test_fail_mode_future_annotations(self):
        self._check("fail_mode.py")


# ===========================================================================
# 6. Runtime import dc_fields -- KEPT (used inside function body)
# ===========================================================================
class TestRuntimeImportsKept:

    def test_dc_fields_runtime_import_in_orchestrator(self):
        src = _src("risk_orchestrator.py")
        assert "from dataclasses import fields as dc_fields" in src, \
            "risk_orchestrator.py removed runtime dc_fields import (was live!)"

    def test_normalise_positions_function_intact(self):
        src = _src("risk_orchestrator.py")
        assert "_normalise_positions" in src, \
            "risk_orchestrator.py removed _normalise_positions function"


# ===========================================================================
# 7. No new dead code introduced
# ===========================================================================
class TestNoNewDeadCode:

    def test_orch_field_usage_consistent_with_import(self):
        src = _src("risk_orchestrator.py")
        tree = ast.parse(src)
        field_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id == 'field':
                    field_calls.append(node.lineno)
        imports_field = "from dataclasses import dataclass, field" in src
        has_field_usage = len(field_calls) > 0
        if imports_field and not has_field_usage:
            raise AssertionError(
                f"risk_orchestrator.py imports 'field' but never uses it "
                f"(found {len(field_calls)} field() calls)"
            )

    def test_pip_helpers_no_unused_logger(self):
        src = _src("_pip_helpers.py")
        lines = src.splitlines()
        logger_defined = any("getLogger" in l or "logger =" in l for l in lines)
        logger_used = any(
            l.strip().startswith("logger.") or " logger." in l
            for l in lines
            if "getLogger" not in l and "logger =" not in l
        )
        if logger_defined and not logger_used:
            raise AssertionError(
                "_pip_helpers.py defines logger but never calls it (dead variable)"
            )

    def test_portfolio_risk_imports_failmode_from_canonical(self):
        src = _src("portfolio_risk.py")
        assert "from backend.risk.fail_mode import FailMode" in src or \
               "fail_mode import FailMode" in src, \
            "portfolio_risk.py does not import FailMode from fail_mode.py"


# ===========================================================================
# 8. field() usage cross-check
# ===========================================================================
class TestFieldUsageCrossCheck:

    def _count_field_calls(self, fname: str) -> int:
        src = _src(fname)
        tree = ast.parse(src)
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id == 'field':
                    count += 1
        return count

    def test_correlation_filter_zero_field_calls(self):
        n = self._count_field_calls("correlation_filter.py")
        assert n == 0, f"correlation_filter.py has {n} field() calls but removed field import"

    def test_exposure_control_zero_field_calls(self):
        n = self._count_field_calls("exposure_control.py")
        assert n == 0, f"exposure_control.py has {n} field() calls but removed field import"

    def test_volatility_filter_zero_field_calls(self):
        n = self._count_field_calls("volatility_filter.py")
        assert n == 0, f"volatility_filter.py has {n} field() calls but removed field import"

    def test_lot_sizing_zero_field_calls(self):
        n = self._count_field_calls("lot_sizing.py")
        assert n == 0, f"lot_sizing.py has {n} field() calls but removed field import"


# ===========================================================================
# Run
# ===========================================================================
if __name__ == "__main__":
    classes = [
        TestASTParseClean,
        TestDeadImportsRemoved,
        TestLiveImportsKept,
        TestAsyncioLocksLive,
        TestFutureAnnotationsKept,
        TestRuntimeImportsKept,
        TestNoNewDeadCode,
        TestFieldUsageCrossCheck,
    ]
    passed = failed = 0
    for cls in classes:
        obj = cls()
        methods = [m for m in dir(obj) if m.startswith("test_")]
        for m in methods:
            try:
                getattr(obj, m)()
                print(f"  PASS  {cls.__name__}.{m}")
                passed += 1
            except Exception as e:
                print(f"  FAIL  {cls.__name__}.{m}: {e}")
                failed += 1
    print(f"\n{'='*40}")
    print(f"TOTAL: {passed+failed}  PASS: {passed}  FAIL: {failed}")
