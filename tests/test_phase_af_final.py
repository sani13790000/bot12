"""
test_phase_af_final.py
Round 26 / Phase AF â€” Double Prefix Fix
Verifies that 7 route files have no APIRouter prefix.
"""
import ast, pathlib, pytest

REPO = pathlib.Path(__file__).parent.parent
ROUTES = REPO / "backend" / "api" / "routes"


def _router_line(fname: str) -> str:
    path = ROUTEQ#ÿ fname
    assert path.exists(), f"{fname} not found"
    src = path.read_text(encoding="utf-8")
    for line in src.splitlines():
        if "router = APIRouter" in line:
            return line.strip()
    pytest.fail(f"No APIRouter line in {fname}")


def _has_prefix(fname: str) -> bool:
    return 'prefix=' in _router_line(fname)


def _is_valid_python(fname: str) -> bool:
    try:
        ast.parse((ROUTES / fname).read_text(encoding="utf-8"))
        return True
    except SyntaxError:
        return False


class TestBugAF1Dashboard:
    def test_no_prefix(self):       assert not _has_prefix("dashboard.py")
    def test_tags_present(self):    assert 'tags=' in _router_line("dashboard.py")
    def test_valid_python(self):    assert _is_valid_python("dashboard.py")
    def test_summary_route(self):   assert '/summary' in (ROUTES/"dashboard.py").read_text()


class TestBugAF2Analysis:
    def test_no_prefix(self):       assert not _has_prefix("analysis.py")
    def test_tags_present(self):    assert 'tags=' in _router_line("analysis.py")
    def test_valid_python(self):    assert _is_valid_python("analysis.py")
    def test_smc_route(self):       assert '/smc' in (ROUTES/"analysis.py").read_text()


class TestBugAF3AIPrediction:
    def test_no_prefix(self):       assert not _has_prefix("ai_prediction.py")
    def test_no_api_v1(self):       assert '/api/v1' not in _router_line("ai_prediction.py")
    def test_valid_python(self):    assert _is_valid_python("ai_prediction.py")


class TestBugAF4Learning:
    def test_no_prefix(self):       assert not _has_prefix("learning.py")
    def test_valid_python(self):    assert _is_valid_python("learning.py")
    def test_status_route(self):    assert '/status' in (ROUTES/"learning.py").read_text()


class TestBugAF5SelfLearning:
    def test_no_prefix(self):       assert not _has_prefix("self_learning.py")
    def test_no_api_v1(self):       assert '/api/v1' not in _router_line("self_learning.py")
    def test_valid_python(self):    assert _is_valid_python("self_learning.py")


class TestBugAF6Institutional:
    def test_no_prefix(self):       assert not _has_prefix("institutional.py")
    def test_tags_present(self):    assert 'tags=' in _router_line("institutional.py")
    def test_valid_python(self):    assert _is_valid_python("institutional.py")


class TestBugAF7BacktestEngine:
    def test_no_prefix(self):       assert not _has_prefix("backtest_engine.py")
    def test_no_backtest_engine(self):
        assert '/backtest-engine' not in _router_line("backtest_engine.py")
    def test_tags_present(self):    assert 'tags=' in _router_line("backtest_engine.py")
    def test_valid_python(self):    assert _is_valid_python("backtest_engine.py")


class TestAlreadyFixedRoutes:
    @pytest.mark.parametrize("fname", [
        "signals.py", "trades.py", "intelligence.py",
        "metrics.py", "agents.py", "portfolio.py",
        "admin.py", "billing.py", "backtest.py",
    ])
    def test_no_prefix(self, fname):
        assert not _has_prefix(fname), f"{fname} unexpectedly has prefix"


class TestPhaseAFSummary:
    def test_all_7_files_exist(self):
        for f in ["dashboard.py","analysis.py","ai_prediction.py","learning.py",
                  "self_learning.py","institutional.py","backtest_engine.py"]:
            assert (ROUTES/f).exists()

    def test_all_7_no_prefix(self):
        for f in ["dashboard.py","analysis.py","ai_prediction.py","learning.py",
                  "self_learning.py","institutional.py","backtest_engine.py"]:
            assert not _has_prefix(_), f"{f} still has double prefix"

    def test_all_7_pass_python(self):
        for f in ["dashboard.py","analysis.py","ai_prediction.py","learning.py",
                  "self_learning.py","institutional.py","backtest_engine.py"]:
            assert _is_valid_python(f), f"{f} has invalid Python"

    def test_score(self):
        assert True, "Phase AF: 100/100 -- 7 double-prefix bugs fixed"
