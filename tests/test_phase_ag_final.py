"""
test_phase_ag_final.py
Phase AG final tests -- BUG-AG1 websocket double prefix, BUG-AG2 institutional_backtest prefix, BUG-AG3 security_ai_loader.router
"""
import ast
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(path):
    with open(os.path.join(BASE, path), encoding="utf-8") as f:
        return f.read()


class TestBugAG1WebsocketDoublePrefix:
    """BUG-AG1: websocket_routes.py had prefix='/ws' -- double prefix /ws/ws/*"""

    def test_file_exists(self):
        path = os.path.join(BASE, "backend/api/routes/websocket_routes.py")
        assert os.path.exists(path), "websocket_routes.py must exist"

    def test_no_prefix_in_router(self):
        content = read("backend/api/routes/websocket_routes.py")
        assert 'prefix="/ws"' not in content, "websocket_routes.py must not have prefix='/ws' in APIRouter"
        assert "prefix='/ws'" not in content

    def test_has_tags_websocket(self):
        content = read("backend/api/routes/websocket_routes.py")
        assert 'tags=["websocket"]' in content or "tags=['websocket']" in content

    def test_router_line_correct(self):
        content = read("backend/api/routes/websocket_routes.py")
        assert 'router = APIRouter(tags=["websocket"])' in content or "router = APIRouter(tags=['websocket'])" in content

    def test_valid_python(self):
        content = read("backend/api/routes/websocket_routes.py")
        ast.parse(content)

    def test_has_ws_endpoints(self):
        content = read("backend/api/routes/websocket_routes.py")
        assert '@router.websocket("/positions")' in content or "@router.websocket('/positions')" in content

    def test_not_placeholder(self):
        content = read("backend/api/routes/websocket_routes.py")
        assert len(content) > 500, f"websocket_routes.py too short: {len(content)} bytes"


class TestBugAG2InstitutionalBacktestPrefix:
    """BUG-AG2: institutional_backtest.py had prefix='/api/v1/institutional-backtest' -- broken path"""

    def test_file_exists(self):
        path = os.path.join(BASE, "backend/api/routes/institutional_backtest.py")
        assert os.path.exists(path)

    def test_no_broken_prefix(self):
        content = read("backend/api/routes/institutional_backtest.py")
        assert 'prefix="/api/v1/institutional-backtest"' not in content
        assert "prefix='/api/v1/institutional-backtest'" not in content

    def test_has_tags_only(self):
        content = read("backend/api/routes/institutional_backtest.py")
        assert 'tags=["Institutional Backtest"]' in content or "tags=['Institutional Backtest']" in content

    def test_router_no_prefix(self):
        content = read("backend/api/routes/institutional_backtest.py")
        lines = content.split("\n")
        router_lines = [l for l in lines if "router = APIRouter" in l]
        assert len(router_lines) >= 1
        for l in router_lines:
            assert 'prefix=' not in l, f"institutional_backtest router must not have prefix: {l}"

    def test_has_run_endpoint(self):
        content = read("backend/api/routes/institutional_backtest.py")
        assert '@router.post("/run")' in content or "@router.post('/run')" in content

    def test_valid_python(self):
        content = read("backend/api/routes/institutional_backtest.py")
        ast.parse(content)

    def test_not_placeholder(self):
        content = read("backend/api/routes/institutional_backtest.py")
        assert len(content) > 1000


class TestBugAG3SecurityAiLoaderRouter:
    """BUG-AG3: main.py had security_ai_loader.router -- AttributeError at startup"""

    def test_main_exists(self):
        assert os.path.exists(os.path.join(BASE, "backend/api/main.py"))

    def test_no_security_ai_loader_router(self):
        content = read("backend/api/main.py")
        assert "security_ai_loader.router" not in content, "main.py must not reference security_ai_loader.router (no .router attr)"

    def test_security_ai_registered_directly(self):
        content = read("backend/api/main.py")
        assert "security_ai.router" in content
        assert "security_ai_extended.router" in content

    def test_websocket_registered_with_ws_prefix(self):
        content = read("backend/api/main.py")
        assert 'prefix="/ws"' in content or "prefix='/ws'" in content

    def test_institutional_backtest_registered(self):
        content = read("backend/api/main.py")
        assert "institutional_backtest.router" in content
        assert 'prefix="/institutional-backtest"' in content or "prefix='/institutional-backtest'" in content

    def test_valid_python(self):
        content = read("backend/api/main.py")
        ast.parse(content)


class TestPhaseAGSummary:
    """Summary tests for Phase AG"""

    def test_all_three_bugs_fixed(self):
        ws = read("backend/api/routes/websocket_routes.py")
        ib = read("backend/api/routes/institutional_backtest.py")
        main = read("backend/api/main.py")
        assert 'prefix="/ws"' not in ws, "AG1: websocket double prefix must be removed"
        assert 'prefix="/api/v1/institutional-backtest"' not in ib, "AG2: institutional_backtest broken prefix must be removed"
        assert "security_ai_loader.router" not in main, "AG3: security_ai_loader.router must not be in main.py"

    def test_effective_paths_correct(self):
        main = read("backend/api/main.py")
        # websocket: main provides /ws, router has no prefix -> /ws/positions OK
        assert 'prefix="/ws"' in main
        # institutional-backtest: main provides /institutional-backtest, router has no prefix
        assert 'prefix="/institutional-backtest"' in main

    def test_all_files_valid_python(self):
        for p in ["backend/api/routes/websocket_routes.py", "backend/api/routes/institutional_backtest.py", "backend/api/main.py"]:
            content = read(p)
            ast.parse(content)

    def test_no_placeholders(self):
        for p in ["backend/api/routes/websocket_routes.py", "backend/api/routes/institutional_backtest.py", "backend/api/main.py"]:
            content = read(p)
            assert "MAIN_CONTENT" not in content
            assert "RESEARCH_CONTENT" not in content
            assert "AUDIT_CONTENT" not in content
            assert len(content) > 500

    def test_score_100(self):
        ws = read("backend/api/routes/websocket_routes.py")
        ib = read("backend/api/routes/institutional_backtest.py")
        main = read("backend/api/main.py")
        bugs_fixed = sum([
            'prefix="/ws"' not in ws,
            'prefix="/api/v1/institutional-backtest"' not in ib,
            "security_ai_loader.router" not in main,
        ])
        assert bugs_fixed == 3, f"Expected 3 bugs fixed, got {bugs_fixed}"
