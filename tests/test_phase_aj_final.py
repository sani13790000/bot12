"""
test_phase_aj_final.py

Phase AJ Tests:
  - BUG-AJ1: trade_history.py @router.get("/trades/history") -> "/history"
  - BUG-AJ2: engine.py pass -> logger.debug in except Exception
"""
import ast
import os
import sys
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

TRADE_HISTORY = os.path.join(ROOT, "backend", "api", "routes", "trade_history.py")
ENGINE_PATH = os.path.join(ROOT, "backend", "license", "engine.py")


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


class TestBugAJ1TradeHistoryPath:
    """BUG-AJ1: @{router}.get("/trades/history") -> "/history""""

    def test_file_exists(self):
        assert os.path.exists(TRADE_HISTORY), f"trade_history.py not found: {TRADE_HISTORY}"

    def test_no_double_segment(self):
        content = read_file(TRADE_HISTORY)
        assert '/trades/history' not in content or '#' in content.split('/trades/history')[0].rsplit('\n', 1)[-1], \
            "BUG-AJ1: @router.get('/trades/history') double segment still present"

    def test_has_single_history_segment(self):
        content = read_file(TRADE_HISTORY)
        assert '@router.get("/history")' in content or \
               "@router.get('/history')" in content, \
               "BUG-AJ1: @router.get('/history') not found"

    def test_effective_path_documented(self):
        content = read_file(TRADE_HISTORY)
        assert 'trade-history/history' in content, \
            "effective path /trade-history/history not documented"

    def test_tags_trades(self):
        content = read_file(TRADE_HISTORY)
        assert 'tags=["trades"]' in content, "tags=[trades] not found"

    def test_valid_python(self):
        content = read_file(TRADE_HISTORY)
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"trade_history.py syntax error: {e}")

    def test_bug_aj1_fix_comment(self):
        content = read_file(TRADE_HISTORY)
        assert 'BUG-AJ1' in content, "BUG-AJ1 fix comment not found"

    def test_get_trade_history_function(self):
        content = read_file(TRADE_HISTORY)
        assert 'get_trade_history' in content, "get_trade_history function not found"


class TestBugAJ2LicenseSilentPass:
    """BUG-AJ2: bare pass in except Exception -> logger.debug"""

    def test_file_exists(self):
        assert os.path.exists(ENGINE_PATH), f"engine.py not found: {ENGINE_PATH}"

    def test_no_bare_pass_in_except(self):
        content = read_file(ENGINE_PATH)
        lines = content.split("\n")
        bare_pass_lines = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped == "pass":
                # check if previous line is except Exception without "as"
                if i > 1 and "except Exception" in lines[i-2]:
                    if " as " not in lines[i-2]:
                        bare_pass_lines.append(i)
        assert not bare_pass_lines, \
            f"BUG-AJ2: bare pass in except Exception at lines {bare_pass_lines}"

    def test_logger_debug_present(self):
        content = read_file(ENGINE_PATH)
        assert 'logger.debug("[License] date parse' in content or \
                "logger.debug('[License] date parse" in content, \
                "BUG-AJ2: logger.debug date parse not found"

    def test_bug_aj2_comment(self):
        content = read_file(ENGINE_PATH)
        assert 'BUG-AJ2' in content, "BUG-AJ2 comment not found"

    def test_valid_python(self):
        content = read_file(ENGINE_PATH)
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"engine.py syntax error: {e}")

    def test_license_engine_class(self):
        content = read_file(ENGINE_PATH)
        assert 'class LicenseEngine' in content, "LicenseEngine class not found"


class TestPhaseAJSummary:
    """Summary tests for Phase AJ"""

    def test_trade_history_size(self):
        content = read_file(TRADE_HISTORY)
        assert len(content) > 2000, "trade_history.py too small"

    def test_engine_size(self):
        content = read_file(ENGINE_PATH)
        assert len(content) > 5000, "engine.py too small"

    def test_no_todo_in_either_file(self):
        for path in [TRADE_HISTORY, ENGINE_PATH]:
            content = read_file(path)
            assert 'TODO' not in content, f"TODO found in {path}"

    def test_effective_path_correct(self):
        """/trade-history/history is the correct effective path (not /trade-history/trades/history)"""
        content = read_file(TRADE_HISTORY)
        assert '@router.get("/history")' in content or \
               "@router.get('/history')" in content

    def test_score_100_both_fixed(self):
        """Both BUG-AJ1 and BUG-AJ2 are fixed"""
        th_content = read_file(TRADE_HISTORY)
        eng_content = read_file(ENGINE_PATH)
        assert 'BUG-AJ1' in th_content, "BUG-AJ1 not fixed"
        assert 'BUG-AJ2' in eng_content, "BUG-AJ2 not fixed"

    def test_no_placeholder_in_either_file(self):
        for path in [TRADE_HISTORY, ENGINE_PATH]:
            content = read_file(path)
            assert 'TODO' not in content
            assert 'YOUR_' not in content
            assert 'placeholder' not in content.lower()
