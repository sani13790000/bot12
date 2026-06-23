"""
test_fix7_dead_code.py
======================
FIX #7 -- Remove Dead Code
Verifies that all identified dead code has been removed and
all downstream behaviour is preserved.

Dead code removed:
  D-1  volatility_filter.py  -- local FailMode class (duplicate)
  D-2  portfolio_risk.py     -- local FailMode class (duplicate)
  D-3  _pip_helpers.py       -- unused logger variable  L
  D-4  _pip_helpers.py       -- unused  import logging
  D-6  volatility_filter.py  -- getattr + == replaced with _coerce_fail_mode + is

NOT removed (proven used):
  correlation_engine.py  asyncio.Lock  -- used at lines 132, 144, 163
  lot_sizing.py          asyncio.Lock  -- used at lines 48, 54
  lot_sizing.py          math / time   -- used
  risk_orchestrator.py   _price_to_pips -- used in SL conversion
"""
import ast
import pathlib
import sys

# locate production risk package
_HERE = pathlib.Path(__file__).parent
_RISK = _HERE.parent / "risk"
assert _RISK.exists(), f"Cannot find backend/risk from {_HERE}"


def _src(name):
    return (_RISK / name).read_text()


def _ast(name):
    return ast.parse(_src(name))


# D-1: volatility_filter.py -- local FailMode class removed
def test_d1_vf_no_local_failmode_class():
    src = _src("volatility_filter.py")
    tree = ast.parse(src)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FailMode":
            raise AssertionError(
                f"volatility_filter.py still defines a local FailMode class at line {node.lineno}"
            )


def test_d1_vf_imports_failmode_from_fail_mode():
    src = _src("volatility_filter.py")
    assert "from backend.risk.fail_mode import FailMode" in src


def test_d1_vf_uses_coerce_not_getattr_eq():
    src = _src("volatility_filter.py")
    assert 'fail_mode = getattr(self._cfg, "fail_mode"' not in src
    assert "_coerce_fail_mode" in src
    assert "is FailMode.FAIL_CLOSED" in src


# D-2: portfolio_risk.py -- local FailMode class removed
def test_d2_pr_no_local_failmode_class():
    src = _src("portfolio_risk.py")
    tree = ast.parse(src)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FailMode":
            raise AssertionError(
                f"portfolio_risk.py still defines a local FailMode class at line {node.lineno}"
            )


def test_d2_pr_imports_failmode_from_fail_mode():
    src = _src("portfolio_risk.py")
    assert "from backend.risk.fail_mode import FailMode" in src


# D-3 + D-4: _pip_helpers.py -- unused logger L and import logging removed
def test_d3_pip_no_unused_logger_L():
    src = _src("_pip_helpers.py")
    assert "L=logging.getLogger" not in src
    assert "L = logging.getLogger" not in src


def test_d4_pip_no_unused_import_logging():
    src = _src("_pip_helpers.py")
    has_log_call = any(
        kw in src for kw in ["logging.getLogger", ".warning(", ".error(",
                              ".info(", ".debug(", ".critical("]
    )
    if not has_log_call:
        assert "import logging" not in src


def test_d4_pip_still_works_without_logging():
    src = _src("_pip_helpers.py")
    tree = ast.parse(src)
    func_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_price_to_pips" in func_names
    assert "_estimate_risk_pct" in func_names


# LIVE: asyncio.Lock in correlation_engine must NOT be removed
def test_live_corr_asyncio_lock_preserved():
    src = _src("correlation_engine.py")
    assert "asyncio.Lock()" in src
    assert "async with self._lock" in src


def test_live_lot_asyncio_lock_preserved():
    src = _src("lot_sizing.py")
    assert "asyncio.Lock()" in src or "_lock" in src


def test_live_lot_math_preserved():
    src = _src("lot_sizing.py")
    assert "math.floor" in src


def test_live_orch_price_to_pips_preserved():
    src = _src("risk_orchestrator.py")
    assert "_price_to_pips" in src


# Single source of truth
def test_failmode_single_source_of_truth():
    local_class_files = []
    for fname in ["volatility_filter.py", "portfolio_risk.py",
                  "exposure_control.py", "risk_orchestrator.py",
                  "correlation_engine.py"]:
        src = _src(fname)
        tree = ast.parse(src)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef) and node.name == "FailMode":
                local_class_files.append(f"{fname}:L{node.lineno}")
    assert local_class_files == [], (
        f"Files still define FailMode at module-level: {local_class_files}"
    )


def test_failmode_py_defines_both_values():
    src = _src("fail_mode.py")
    assert "FAIL_CLOSED" in src
    assert "FAIL_OPEN" in src


def test_failmode_coerce_function_exists():
    src = _src("fail_mode.py")
    assert "def coerce" in src


# Backward-compat
def test_bc_volatility_filter_api_unchanged():
    src = _src("volatility_filter.py")
    assert "def check(" in src
    assert "class VolatilityFilter" in src


def test_bc_portfolio_risk_api_unchanged():
    src = _src("portfolio_risk.py")
    assert "def check(" in src
    assert "class PortfolioRiskManager" in src


def test_bc_pip_helpers_functions_unchanged():
    src = _src("_pip_helpers.py")
    assert "def _price_to_pips" in src
    assert "def _estimate_risk_pct" in src


def test_bc_failmode_try_except_fallback_present():
    for fname in ["volatility_filter.py", "portfolio_risk.py"]:
        src = _src(fname)
        assert "except ImportError" in src


# AST integrity
def test_ast_all_files_parse():
    files = [
        "volatility_filter.py", "portfolio_risk.py", "_pip_helpers.py",
        "fail_mode.py", "exposure_control.py", "risk_orchestrator.py",
        "correlation_engine.py", "lot_sizing.py",
    ]
    errors = []
    for f in files:
        try:
            ast.parse(_src(f))
        except SyntaxError as e:
            errors.append(f"{f}: {e}")
    assert errors == [], "Syntax errors after patch:\n" + "\n".join(errors)


# Extra
def test_no_double_failmode_import():
    for fname in ["volatility_filter.py", "portfolio_risk.py",
                  "exposure_control.py", "risk_orchestrator.py"]:
        src = _src(fname)
        count = src.count("from backend.risk.fail_mode import FailMode")
        assert count <= 1


def test_vf_coerce_used_in_check():
    src = _src("volatility_filter.py")
    idx_check  = src.find("def check(")
    idx_coerce = src.find("_coerce_fail_mode", idx_check)
    assert idx_coerce > idx_check


def test_pr_failmode_used_in_check():
    src = _src("portfolio_risk.py")
    assert "FailMode.FAIL_CLOSED" in src


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {t.__name__}: {e}")
            failed += 1
    print(f"\n{'='*55}")
    print(f"  {passed}/{passed+failed} PASS")
    if failed:
        sys.exit(1)
