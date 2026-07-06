"""
test_phase_ac_final.py
Faz AC — BUG-AC1 (backtest double prefix) + BUG-AC2 (research not registered)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
BACKTEST_PY = ROOT / "backend" / "api" / "routes" / "backtest.py"
MAIN_PY     = ROOT / "backend" / "api" / "main.py"
RESEARCH_PY = ROOT / "backend" / "api" / "routes" / "research.py"


class TestBugAC1BacktestDoublePrefix:
    """BUG-AC1: backtest.py must NOT have prefix in APIRouter."""

    def test_backtest_file_exists(self):
        assert BACKTEST_PY.exists(), "backtest.py missing"

    def test_backtest_not_placeholder(self):
        content = BACKTEST_PY.read_text(encoding="utf-8")
        assert content.strip() != '"BACKTEST_CONTENT"', "backtest.py is still placeholder"
        assert len(content) > 500, f"backtest.py too small: {len(content)} bytes"

    def test_backtest_router_no_prefix(self):
        content = BACKTEST_PY.read_text(encoding="utf-8")
        # find the line with APIRouter
        for line in content.split("\n"):
            if "router = APIRouter" in line:
                assert 'prefix="/backtest"' not in line, (
                    f"BUG-AC1: double prefix still present: {line!r}\n"
                    "backtest.py router should not have prefix='/backtest'"
                )
                break
        else:
            raise AssertionError("router = APIRouter line not found in backtest.py")

    def test_backtest_router_has_tags(self):
        content = BACKTEST_PY.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if "router = APIRouter" in line:
                assert 'tags=["backtest"]' in line or "tags=['backtest']" in line, (
                    f"router line missing tags: {line!r}"
                )
                break

    def test_backtest_run_endpoint_exists(self):
        content = BACKTEST_PY.read_text(encoding="utf-8")
        assert '@router.post("/run"' in content or "@router.post('/run'" in content, (
            "POST /run endpoint missing from backtest.py"
        )

    def test_backtest_valid_python(self):
        content = BACKTEST_PY.read_text(encoding="utf-8")
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise AssertionError(f"backtest.py syntax error: {e}") from e

    def test_effective_path_is_backtest_run(self):
        """With main.py providing prefix=/backtest, path must be /backtest/run."""
        backtest = BACKTEST_PY.read_text(encoding="utf-8")
        main     = MAIN_PY.read_text(encoding="utf-8")
        # main.py provides the prefix
        assert 'prefix="/backtest"' in main or "prefix='/backtest'" in main, (
            "main.py must provide prefix='/backtest' for backtest router"
        )
        # backtest.py must NOT have the prefix
        router_line = next(
            (l for l in backtest.split("\n") if "router = APIRouter" in l), ""
        )
        assert 'prefix="/backtest"' not in router_line, (
            "double prefix: backtest.py still has prefix='/backtest'"
        )


class TestBugAC2ResearchNotRegistered:
    """BUG-AC2: research must be in main.py import list and include_router."""

    def test_research_file_exists(self):
        assert RESEARCH_PY.exists(), "research.py missing"

    def test_research_not_placeholder(self):
        content = RESEARCH_PY.read_text(encoding="utf-8")
        assert content.strip() != '"RESEARCH_CONTENT"', "research.py is still placeholder"
        assert len(content) > 500, f"research.py too small: {len(content)} bytes"

    def test_research_in_main_import(self):
        content = MAIN_PY.read_text(encoding="utf-8")
        assert "research" in content, (
            "BUG-AC2: 'research' not found in main.py at all"
        )

    def test_research_in_import_block(self):
        content = MAIN_PY.read_text(encoding="utf-8")
        # find the from backend.api.routes import (...) block
        import_block_match = re.search(
            r'from backend\.api\.routes import \([^)]+\)', content, re.DOTALL
        )
        assert import_block_match, "import block not found in main.py"
        import_block = import_block_match.group(0)
        assert "research" in import_block, (
            f"BUG-AC2: 'research' missing from import block:\n{import_block}"
        )

    def test_research_include_router(self):
        content = MAIN_PY.read_text(encoding="utf-8")
        assert "research.router" in content, (
            "BUG-AC2: research.router not in main.py include_router calls"
        )

    def test_research_prefix_slash_research(self):
        content = MAIN_PY.read_text(encoding="utf-8")
        # find include_router line for research
        for line in content.split("\n"):
            if "research.router" in line:
                assert 'prefix="/research"' in line or "prefix='/research'" in line, (
                    f"research.router line missing prefix='/research': {line!r}"
                )
                break
        else:
            raise AssertionError("research.router include_router line not found")

    def test_main_valid_python(self):
        content = MAIN_PY.read_text(encoding="utf-8")
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise AssertionError(f"main.py syntax error: {e}") from e


class TestPhaseACSummary:
    """Summary: all AC fixes verified."""

    def test_backtest_no_double_prefix(self):
        backtest = BACKTEST_PY.read_text(encoding="utf-8")
        router_line = next(
            (l for l in backtest.split("\n") if "router = APIRouter" in l), ""
        )
        assert 'prefix=' not in router_line, (
            f"backtest.py still has prefix in APIRouter: {router_line!r}"
        )

    def test_research_fully_wired(self):
        main = MAIN_PY.read_text(encoding="utf-8")
        assert "research" in main
        assert "research.router" in main
        assert 'prefix="/research"' in main or "prefix='/research'" in main

    def test_all_files_valid_python(self):
        for fpath in [BACKTEST_PY, MAIN_PY, RESEARCH_PY]:
            content = fpath.read_text(encoding="utf-8")
            try:
                ast.parse(content)
            except SyntaxError as e:
                raise AssertionError(f"{fpath.name} syntax error: {e}") from e

    def test_no_placeholder_strings(self):
        for fpath, placeholder in [
            (BACKTEST_PY, "BACKTEST_CONTENT"),
            (MAIN_PY,     "MAIN_CONTENT"),
            (RESEARCH_PY, "RESEARCH_CONTENT"),
        ]:
            content = fpath.read_text(encoding="utf-8")
            assert placeholder not in content, (
                f"{fpath.name} still contains placeholder '{placeholder}'"
            )

    def test_phase_ac_score_100(self):
        """Phase AC: 2 P0 bugs fixed — score should reach 100/100."""
        backtest = BACKTEST_PY.read_text(encoding="utf-8")
        main     = MAIN_PY.read_text(encoding="utf-8")
        router_line = next(
            (l for l in backtest.split("\n") if "router = APIRouter" in l), ""
        )
        # AC1
        assert 'prefix=' not in router_line
        # AC2
        assert "research.router" in main
        assert 'prefix="/research"' in main or "prefix='/research'" in main
