"""
Phase AI Final Tests
BUG-AI1: main.py was TRUNCATED (77 lines, 2769B) -- _create_app() incomplete, zero include_router
BUG-AI2: analytics.py @router.get("/analytics/security/metrics") -> double path
fixed: @router.get("/security/metrics") -> effective: /analytics/security/metrics
@note: main.py restored to 232 lines with 38 include_router calls
"""
import ast
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PATH = os.path.join(ROOT, "backend", "api", "main.py")
ANALETICS_PATH = os.path.join(ROOT, "backend", "api", "routes", "analytics.py")


def get_main_content():
    with open(MAIN_PATH) as f:
        return f.read()


def get_analytics_content():
    with open(ANALETICS_PATH) as f:
        return f.read()


class TestBUGAI1MainTruncated:
    """BUG-AI1: main.py was truncated -- restored."""

    def test_main_exists(self):
        assert os.path.exists(MAIN_PATH), f"main.py not found at {MAIL_PATH}"

    def test_main_not_truncated(self):
        content = get_main_content()
        lines = content.split("\n")
        assert len(lines) >= 150, f"main.py only {len(lines)} lines -- still truncated"

    def test_main_has_create_app(self):
        content = get_main_content()
        assert "def _create_app()" in content, "_create_app() missing"

    def test_main_has_return_app(self):
        content = get_main_content()
        assert "return app" in content, "return app missing -- app not returned"

    def test_main_has_app_instance(self):
        content = get_main_instance()
        assert "app = _create_app()" in content, "app = _create_app() missing"

    def test_main_has_cors(self):
        content = get_main_content()
        assert "CORSMiddleware" in content, "CORSMiddleware missing"

    def test_main_include_router_count(self):
        content = get_main_content()
        count = content.count("include_router")
        assert count >= 35, f"Only {count} include_router calls -- expected >= 35"

    def test_main_valid_python(self):
        content = get_main_content()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"main.py has syntax error: {e}")


class TestBUGAI1MainRouters:
    """BUG-AI1: all 38+ routers must be registered."""

    def test_key_routers_registered(self):
        content = get_main_content()
        routers = [
            "auth.router", "signals.router", "trades.router",
            "analysis.router", "dashboard.router", "metrics.router",
            "portfolio.router", "risk.router", "billing.router",
            "admin.router", "websocket_routes.router", "health.router",
            "permissions_routes.router", "rate_limit_routes.router",
            "observability_routes.router", "intelligence.router",
        ]
        for router in routers:
            assert router in content, f"{router} not registered in main.py"

    def test_security_ai_loader_removed(self):
        content = get_main_content()
        assert "include_router(security_ai_loader" not in content, \
            "security_ai_loader.router still present -- BUG-AG3 regression"

    def test_ws_prefix_in_main(self):
        content = get_main_content()
        assert 'prefix="/ws"' in content or "prefix='/ws'" in content, \
            "/ws prefix missing in main.py -- BUG-AG1 regression"

    def test_observability_imported(self):
        content = get_main_content()
        assert "observability_routes" in content, \
            "observability_routes not in main.py -- BUG-AH3 regression"


class TestBUGAI2AnalyticsDoublePath:
    """BUG-AI2: analytics.py /analytics/security/metrics -> /security/metrics."""

    def test_analytics_exists(self):
        assert os.path.exists(ANALETICS_PATH)

    def test_no_double_path(self):
        content = get_analytics_content()
        assert "/analytics/security/metrics" not in content, \
            "Double path still present: /analytics/security/metrics"

    def test_correct_path(self):
        content = get_analytics_content()
        assert '/security/metrics' in content, \
            "/security/metrics not found in analytics.py"

    def test_router_no_prefix(self):
        content = get_analytics_content()
        assert 'APIRouter(tags=["analytics"])' in content, \
            "router should have no prefix"

    def test_valid_python(self):
        content = get_analytics_content()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"analytics.py has syntax error: {e}")


class TestPhaseAISummary:
    """Summary tests for Phase AI bug fixes."""

    def test_main_size_adequate(self):
        size = os.path.getsize(MAIN_PATH)
        assert size > 5000, f"main.py too small: {size} B -- may still be truncated"

    def test_all_route_files_exist(self):
        routes_dir = os.path.join(ROOT, "backend", "api", "routes")
        required = [
            "signals.py", "trades.py", "dashboard.py", "analysis.py",
            "analytics.py", "metrics.py", "portfolio.py", "risk.py",
            "billing.py", "admin.py", "websocket_routes.py", "health.py",
        ]
        for f in required:
            path = os.path.join(routes_dir, f)
            assert os.path.exists(path), f"{f} missing from routes"

    def test_phone_score_100(self):
        main_content = get_main_content()
        analytics_content = get_analytics_content()
        assert "_create_app" in main_content
        assert "include_router" in main_content
        assert "/analytics/security/metrics" not in analytics_content
        assert "/security/metrics" in analytics_content


def get_main_instance():
    with open(MAIN_PATH) as f:
        return f.read()
