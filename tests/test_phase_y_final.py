"""
tests/test_phase_y_final.py
Phase Y Final Tests — BUG-Y1, BUG-Y2, BUG-Y3
"""
import ast
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


# ────────────────────────────────────────────────────────────────────────────────
Helpers
# ────────────────────────────────────────────────────────────────────────────────

def read_file(rel_path: str) -> str:
    with open(os.path.join(REPO_ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def is_valid_python(source: str) -> bool:
    try:
        ast.parse(source)
        return True
    except SyntaxError:
        return False


# ────────────────────────────────────────────────────────────────────────────────
BUG-Y1: BacktestPage StatCard — named import from correct path + real API
# ────────────────────────────────────────────────────────────────────────────────

class TestBugY1BacktestPageStatCard:
    PAGE = "frontend/src/pages/BacktestPage.tsx"

    def test_file_exists(self):
        assert os.path.exists(os.path.join(REPO_ROOT, self.PAGE))

    def test_no_default_import_wrong_path(self):
        content = read_file(self.PAGE)
        assert 'import StatCard from "@/components/StatCard"' not in content, (
            "BUG-Y1: default import from wrong path still present"
        )

    def test_named_import_correct_path(self):
        content = read_file(self.PAGE)
        assert "{ StatCard }" in content
        assert "@/components/common/StatCard" in content

    def test_no_fake_math_random(self):
        content = read_file(self.PAGE)
        assert "Math.random()" not in content, "BUG-Y1: fake Math.random() still present"

    def test_no_fake_settimeout_delay(self):
        content = read_file(self.PAGE)
        assert "1800" not in content, "BUG-Y1: fake setTimeout(1800) delay still present"

    def test_real_api_call(self):
        content = read_file(self.PAGE)
        assert "apiFetch" in content or 'fetch(' in content

    def test_backtest_run_endpoint(self):
        content = read_file(self.PAGE)
        assert "/backtest/run" in content


# ────────────────────────────────────────────────────────────────────────────────
BUG-Y2: MT5Connector silent fallback — critical log added
# ────────────────────────────────────────────────────────────────────────────────

class TestBugY2MT5ConnectorSilentFallback:
    CONNECTOR = "backend/execution/mt5_connector.py"

    def test_file_exists(self):
        assert os.path.exists(os.path.join(REPO_ROOT, self.CONNECTOR))

    def test_is_valid_python(self):
        assert is_valid_python(read_file(self.CONNECTOR))

    def test_critical_log_present(self):
        content = read_file(self.CONNECTOR)
        assert "logger.critical" in content, "BUG-Y2: logger.critical missing"

    def test_critical_mentions_demo(self):
        content = read_file(self.CONNECTOR)
        assert "DEMO" in content or "demo" in content.lower(), "BUG-Y2: critical message should mention DEMO"

    def test_demo_fallback_still_exists(self):
        content = read_file(self.CONNECTOR)
        assert "MT5Connector(demo=True)" in content

    def test_no_silent_except_block(self):
        content = read_file(self.CONNECTOR)
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped in ("except Exception:", ) or stripped.startswith("except Exception as "):
                block = "\n".join(lines[i:i+6])
                if "MT5Connector(demo=True)" in block:
                    assert "logger" in block, (
                        f"BUG-Y2: silent except at line {i+1}"
                    )


# ────────────────────────────────────────────────────────────────────────────────
BUG-Y3: deps.py _stub_verify_token scope
# ────────────────────────────────────────────────────────────────────────────────

class TestBugY3DepsStubScope:
    DEPS = "backend/core/deps.py"

    def test_file_exists(self):
        assert os.path.exists(os.path.join(REPO_ROOT, self.DEPS))

    def test_is_valid_python(self):
        assert is_valid_python(read_file(self.DEPS))

    def test_get_current_user_uses_verify_jwt(self):
        content = read_file(self.DEPS)
        assert "verify_jwt" in content

    def test_stub_not_in_get_current_user(self):
        content = read_file(self.DEPS)
        lines = content.split("\n")
        in_fn = False
        for line in lines:
            if "async def get_current_user" in line:
                in_fn = True
            elif in_fn and line.startswith("async def "):
                in_fn = False
            if in_fn and "_stub_verify_token" in line and not line.strip().startswith("#"):
                pytest.fail("BUG-Y3: get_current_user uses _stub_verify_token")


# ────────────────────────────────────────────────────────────────────────────────
Summary
# ────────────────────────────────────────────────────────────────────────────────

class TestPhaseYSummary:

    def test_backtest_page_no_mock_numbers(self):
        content = read_file("frontend/src/pages/BacktestPage.tsx")
        for mock_val in ["Math.random()", "setTimeout", "win_rate: 67.4", "profit_factor: 1.82"]:
            assert mock_val not in content, f"Mock data still present: {mock_val}"

    def test_all_pages_statcard_named_import(self):
        pages_dir = os.path.join(REPO_ROOT, "frontend/src/pages")
        if not os.path.exists(pages_dir):
            pytest.skip("frontend pages dir not found")
        wrong = []
        for fname in os.listdir(pages_dir):
            if not fname.endswith(".tsx"):
                continue
            fpath = os.path.join(pages_dir, fname)
            with open(fpath, encoding="utf-8") as f:
                c = f.read()
            if 'import StatCard from "@/components/StatCard"' in c:
                wrong.append(fname)
        assert not wrong, f"Wrong StatCard import in: {wrong}"

    def test_mt5_connector_valid_python(self):
        assert is_valid_python(read_file("backend/execution/mt5_connector.py"))

    def test_deps_valid_python(self):
        assert is_valid_python(read_file("backend/core/deps.py"))
