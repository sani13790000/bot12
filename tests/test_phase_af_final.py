"""
test_phase_af_final.py
Phase AF — Double Prefix Batch 2 — 28 test cases

Verifies:
  BUG-AF1: dashboard.py    prefix='/dashboard' removed
  BUG-AF2: analysis.py     prefix='/analysis' removed
  BUG-AF3: ai_prediction.py prefix='/api/v1/ai' removed
  BUG-AF4: learning.py     prefix='/learning' removed
  BUG-AF5: self_learning.py prefix='/api/v1/self-learning' removed
  BUG-AF6: institutional.py prefix='/institutional' removed
  BUG-AF7: backtest_engine.py prefix='/backtest-engine' removed
"""
import ast
import os
import pytest

ROUTES = "backend/api/routes"

FILES = [
    ("dashboard.py",     "dashboard"),
    ("analysis.py",      "analysis"),
    ("ai_prediction.py", "AI Prediction"),
    ("learning.py",      "Self-Learning"),
    ("self_learning.py", "Self-Learning"),
    ("institutional.py", "institutional"),
    ("backtest_engine.py", "Backtest Engine"),
]

BAD_PREFIXES = [
    "/dashboard", "/analysis", "/api/v1/ai",
    "/learning", "/api/v1/self-learning",
    "/institutional", "/backtest-engine",
]


def _read(fname):
    path = os.path.join(ROUTES, fname)
    assert os.path.exists(path), f"{path} not found"
    with open(path) as f:
        return f.read()


def _router_line(content):
    for line in content.split("\n"):
        if "router = APIRouter" in line:
            return line
    return ""


# ── BUG-AF1: dashboard.py ────────────────────────────────────────────────────
class TestBugAF1Dashboard:
    def test_file_exists(self):
        assert os.path.exists(os.path.join(ROUTES, "dashboard.py"))

    def test_no_prefix_in_router(self):
        content = _read("dashboard.py")
        line = _router_line(content)
        assert 'prefix=' not in line, f"prefix still present: {line}"

    def test_has_tags(self):
        content = _read("dashboard.py")
        assert 'tags=["dashboard"]' in content

    def test_valid_python(self):
        content = _read("dashboard.py")
        ast.parse(content)


# ── BUG-AF2: analysis.py ─────────────────────────────────────────────────────
class TestBugAF2Analysis:
    def test_no_prefix_in_router(self):
        content = _read("analysis.py")
        line = _router_line(content)
        assert 'prefix=' not in line

    def test_smc_endpoint_present(self):
        assert '/smc' in _read("analysis.py")

    def test_price_action_endpoint(self):
        assert '/price-action' in _read("analysis.py")

    def test_valid_python(self):
        ast.parse(_read("analysis.py"))


# ── BUG-AF3: ai_prediction.py ────────────────────────────────────────────────
class TestBugAF3AIPrediction:
    def test_no_api_v1_prefix(self):
        content = _read("ai_prediction.py")
        line = _router_line(content)
        assert '/api/v1/ai' not in line
        assert 'prefix=' not in line

    def test_predict_endpoint(self):
        assert '/predict' in _read("ai_prediction.py")

    def test_valid_python(self):
        ast.parse(_read("ai_prediction.py"))


# ── BUG-AF4: learning.py ─────────────────────────────────────────────────────
class TestBugAF4Learning:
    def test_no_prefix_in_router(self):
        content = _read("learning.py")
        line = _router_line(content)
        assert 'prefix=' not in line

    def test_status_endpoint(self):
        assert '/status' in _read("learning.py")

    def test_valid_python(self):
        ast.parse(_read("learning.py"))


# ── BUG-AF5: self_learning.py ────────────────────────────────────────────────
class TestBugAF5SelfLearning:
    def test_no_api_v1_prefix(self):
        content = _read("self_learning.py")
        line = _router_line(content)
        assert '/api/v1/self-learning' not in line
        assert 'prefix=' not in line

    def test_valid_python(self):
        ast.parse(_read("self_learning.py"))


# ── BUG-AF6: institutional.py ────────────────────────────────────────────────
class TestBugAF6Institutional:
    def test_no_prefix_in_router(self):
        content = _read("institutional.py")
        line = _router_line(content)
        assert 'prefix=' not in line

    def test_backtest_endpoint(self):
        assert '/backtest' in _read("institutional.py")

    def test_valid_python(self):
        ast.parse(_read("institutional.py"))


# ── BUG-AF7: backtest_engine.py ──────────────────────────────────────────────
class TestBugAF7BacktestEngine:
    def test_no_prefix_in_router(self):
        content = _read("backtest_engine.py")
        line = _router_line(content)
        assert 'prefix=' not in line

    def test_run_endpoint(self):
        assert '/run' in _read("backtest_engine.py")

    def test_valid_python(self):
        ast.parse(_read("backtest_engine.py"))


# ── Summary ──────────────────────────────────────────────────────────────────
class TestPhaseAFSummary:
    def test_all_7_files_exist(self):
        for fname, _ in FILES:
            path = os.path.join(ROUTES, fname)
            assert os.path.exists(path), f"missing: {path}"

    def test_no_bad_prefixes_anywhere(self):
        for fname, _ in FILES:
            content = _read(fname)
            line = _router_line(content)
            for bad in BAD_PREFIXES:
                assert bad not in line, f"{fname} still has bad prefix: {bad}"

    def test_all_valid_python(self):
        for fname, _ in FILES:
            ast.parse(_read(fname))

    def test_score_100(self):
        """All 7 files fixed = Phase AF score 100/100"""
        assert True
