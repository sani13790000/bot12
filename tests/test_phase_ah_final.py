"""
Phase AH Final Tests
====================
BUG-AH1: permissions_routes.py -- added APIRouter + @router decorators
BUG-AH2: rate_limit_routes.py  -- added APIRouter + @router decorators
BUG-AH3: main.py               -- observability_routes registered
"""
from __future__ import annotations
import ast
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# BUG-AH1: permissions_routes.py must have router attribute
# ---------------------------------------------------------------------------
class TestBugAH1PermissionsRouter:
    """permissions_routes.py must have APIRouter + @router endpoints."""

    def _content(self) -> str:
        p = ROOT / "backend/api/routes/permissions_routes.py"
        assert p.exists(), f"Missing: {p}"
        return p.read_text(encoding="utf-8")

    def test_has_apiRouter_import(self):
        assert "APIRouter" in self._content(), "Must import APIRouter"

    def test_has_router_assignment(self):
        content = self._content()
        assert "router = APIRouter" in content, "Must have router = APIRouter(...)"

    def test_has_router_get_decorators(self):
        content = self._content()
        assert "@router.get" in content, "Must have @router.get decorators"

    def test_has_matrix_endpoint(self):
        assert "/matrix" in self._content(), "Must have /matrix endpoint"

    def test_has_my_endpoint(self):
        assert "/my" in self._content(), "Must have /my endpoint"

    def test_has_roles_endpoint(self):
        assert "/roles" in self._content(), "Must have /roles endpoint"

    def test_no_plain_functions_only(self):
        content = self._content()
        # Must have router, not just plain def
        assert "router = APIRouter" in content
        assert "@router" in content

    def test_valid_python(self):
        content = self._content()
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise AssertionError(f"SyntaxError: {e}")


# ---------------------------------------------------------------------------
# BUG-AH2: rate_limit_routes.py must have router attribute
# ---------------------------------------------------------------------------
class TestBugAH2RateLimitRouter:
    """rate_limit_routes.py must have APIRouter + @router endpoints."""

    def _content(self) -> str:
        p = ROOT / "backend/api/routes/rate_limit_routes.py"
        assert p.exists(), f"Missing: {p}"
        return p.read_text(encoding="utf-8")

    def test_has_apiRouter_import(self):
        assert "APIRouter" in self._content(), "Must import APIRouter"

    def test_has_router_assignment(self):
        content = self._content()
        assert "router = APIRouter" in content, "Must have router = APIRouter(...)"

    def test_has_router_decorators(self):
        content = self._content()
        assert "@router." in content, "Must have @router decorators"

    def test_has_stats_endpoint(self):
        assert "/stats" in self._content(), "Must have /stats endpoint"

    def test_has_bans_endpoint(self):
        assert "/bans" in self._content(), "Must have /bans endpoint"

    def test_has_tiers_endpoint(self):
        assert "/tiers" in self._content(), "Must have /tiers endpoint"

    def test_no_class_only(self):
        content = self._content()
        # Must have router, not just class
        assert "router = APIRouter" in content
        assert "@router" in content

    def test_valid_python(self):
        content = self._content()
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise AssertionError(f"SyntaxError: {e}")


# ---------------------------------------------------------------------------
# BUG-AH3: observability_routes must be registered in main.py
# ---------------------------------------------------------------------------
class TestBugAH3ObservabilityRegistered:
    """observability_routes must be imported and registered in main.py."""

    def _content(self) -> str:
        p = ROOT / "backend/api/main.py"
        assert p.exists(), f"Missing: {p}"
        return p.read_text(encoding="utf-8")

    def test_observability_import(self):
        content = self._content()
        assert "observability_routes" in content, "Must import observability_routes"

    def test_observability_include_router(self):
        content = self._content()
        assert "observability_routes.router" in content, \
            "Must call app.include_router(observability_routes.router)"

    def test_observability_routes_file_has_router(self):
        p = ROOT / "backend/api/observability_routes.py"
        assert p.exists(), f"Missing: {p}"
        content = p.read_text(encoding="utf-8")
        assert "router = APIRouter" in content, "observability_routes.py must have APIRouter"

    def test_observability_prefix_in_router(self):
        p = ROOT / "backend/api/observability_routes.py"
        content = p.read_text(encoding="utf-8")
        assert "/observability" in content, "Must have /observability prefix"

    def test_valid_python_main(self):
        content = self._content()
        try:
            ast.parse(content)
        except SyntaxError as e:
            raise AssertionError(f"SyntaxError in main.py: {e}")


# ---------------------------------------------------------------------------
# Phase AH Summary
# ---------------------------------------------------------------------------
class TestPhaseAHSummary:
    """All Phase AH fixes in one place."""

    def test_permissions_routes_has_router(self):
        p = ROOT / "backend/api/routes/permissions_routes.py"
        content = p.read_text(encoding="utf-8")
        assert "router = APIRouter" in content
        assert "@router.get" in content

    def test_rate_limit_routes_has_router(self):
        p = ROOT / "backend/api/routes/rate_limit_routes.py"
        content = p.read_text(encoding="utf-8")
        assert "router = APIRouter" in content
        assert "@router." in content

    def test_observability_registered_in_main(self):
        p = ROOT / "backend/api/main.py"
        content = p.read_text(encoding="utf-8")
        assert "observability_routes.router" in content

    def test_no_plain_function_router_issue(self):
        """Neither permissions nor rate_limit should be plain functions only."""
        for fname in ["permissions_routes", "rate_limit_routes"]:
            p = ROOT / f"backend/api/routes/{fname}.py"
            content = p.read_text(encoding="utf-8")
            assert "router = APIRouter" in content, \
                f"{fname}.py must have APIRouter"

    def test_score_100(self):
        """All 3 BUG-AH fixes verified."""
        checks = [
            (ROOT / "backend/api/routes/permissions_routes.py", "router = APIRouter"),
            (ROOT / "backend/api/routes/rate_limit_routes.py", "router = APIRouter"),
            (ROOT / "backend/api/main.py", "observability_routes.router"),
        ]
        for path, pattern in checks:
            content = path.read_text(encoding="utf-8")
            assert pattern in content, f"{path.name}: missing '{pattern}'"
