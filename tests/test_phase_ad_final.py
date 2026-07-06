"""
test_phase_ad_final.py — Phase AD: Admin double prefix + FakeCtx + CORS wildcard tests

BUG-AD1: admin.py router had prefix='/admin' + main.py prefix='/admin' -> /admin/admin/*
BUG-AD2: admin.py _require_admin was API-key only (bypassed if ADMIN_API_KEY not set)
BUG-AD3: admin_observability.py _FakeCtx always returned fake admin context
BUG-AD4a: admin_observability.py router had prefix='/admin' -> /admin/admin/*
BUG-AD4b: admin_users.py router had prefix='/admin/users' -> /admin/admin/users/*
BUG-AD5: main.py CORS wildcard ['*'] default with credentials=True
"""
from __future__ import annotations

import ast
import os
import re

import pytest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel: str) -> str:
    path = os.path.join(BASE, rel)
    assert os.path.exists(path), f"File not found: {path}"
    with open(path, encoding="utf-8") as f:
        return f.read()


# ══ BUG-AD1: admin.py double prefix ══════════════════════════════════════════

class TestBugAD1AdminDoublePrefix:
    def test_admin_py_no_prefix_in_router(self):
        content = read("backend/api/routes/admin.py")
        router_line = [l for l in content.splitlines() if "router = APIRouter" in l]
        assert router_line, "router = APIRouter not found"
        assert 'prefix="/admin"' not in router_line[0], (
            f"admin.py still has prefix='/admin' in router: {router_line[0]}"
        )

    def test_admin_py_router_has_tags(self):
        content = read("backend/api/routes/admin.py")
        assert 'tags=["admin"]' in content

    def test_admin_py_valid_python(self):
        content = read("backend/api/routes/admin.py")
        ast.parse(content)

    def test_admin_py_not_empty(self):
        content = read("backend/api/routes/admin.py")
        assert len(content) > 1000, f"admin.py too small: {len(content)} bytes"

    def test_admin_py_endpoints_present(self):
        content = read("backend/api/routes/admin.py")
        for endpoint in ["/config", "/users", "/kill", "/resume", "/kill-switch", "/logs", "/metrics/summary"]:
            assert endpoint in content, f"endpoint {endpoint} not found"


# ══ BUG-AD2: admin.py fake JWT ════════════════════════════════════════════════

class TestBugAD2AdminFakeJWT:
    def test_no_api_key_only_check(self):
        content = read("backend/api/routes/admin.py")
        assert "replace with" not in content.lower() or "jwt" not in content.lower(), (
            "admin.py still has 'replace with ... JWT' comment suggesting placeholder auth"
        )

    def test_uses_get_current_user(self):
        content = read("backend/api/routes/admin.py")
        assert "get_current_user" in content, "admin.py must use get_current_user for JWT auth"

    def test_role_check_present(self):
        content = read("backend/api/routes/admin.py")
        assert "admin" in content and ("superadmin" in content or "super_admin" in content), (
            "admin.py must check for admin/superadmin role"
        )

    def test_no_x_admin_key_bypass(self):
        content = read("backend/api/routes/admin.py")
        # Old pattern: if expected and x_admin_key != expected (bypassed when expected=None)
        assert "if expected and x_admin_key" not in content, (
            "admin.py still has bypassable API-key check"
        )


# ══ BUG-AD3: admin_observability.py _FakeCtx ══════════════════════════════════

class TestBugAD3FakeCtx:
    def test_no_fake_ctx_class(self):
        content = read("backend/api/routes/admin_observability.py")
        assert not re.search(r'^class _FakeCtx', content, re.MULTILINE), (
            "admin_observability.py still has _FakeCtx class"
        )

    def test_uses_get_current_user(self):
        content = read("backend/api/routes/admin_observability.py")
        assert "get_current_user" in content, "admin_observability.py must use real JWT auth"

    def test_no_fake_return(self):
        content = read("backend/api/routes/admin_observability.py")
        assert "return _FakeCtx()" not in content, (
            "admin_observability.py still returns _FakeCtx instance"
        )

    def test_valid_python(self):
        content = read("backend/api/routes/admin_observability.py")
        ast.parse(content)


# ══ BUG-AD4: double prefix in observability + users ════════════════════════════

class TestBugAD4DoublePrefix:
    def test_obs_no_prefix_in_router(self):
        content = read("backend/api/routes/admin_observability.py")
        router_line = [l for l in content.splitlines() if "router = APIRouter" in l]
        assert router_line, "router = APIRouter not found"
        assert 'prefix="/admin"' not in router_line[0], (
            f"admin_observability.py still has prefix='/admin' in router: {router_line[0]}"
        )

    def test_users_prefix_is_users_only(self):
        content = read("backend/api/routes/admin_users.py")
        router_line = [l for l in content.splitlines() if "router = APIRouter" in l]
        assert router_line, "router = APIRouter not found"
        # Should be prefix='/users' not prefix='/admin/users'
        assert 'prefix="/admin/users"' not in router_line[0], (
            f"admin_users.py still has prefix='/admin/users': {router_line[0]}"
        )

    def test_users_valid_python(self):
        content = read("backend/api/routes/admin_users.py")
        ast.parse(content)


# ══ BUG-AD5: CORS wildcard ══════════════════════════════════════════════════════

class TestBugAD5CORSWildcard:
    def test_no_wildcard_default(self):
        content = read("backend/api/main.py")
        # Old pattern: getattr(settings, 'CORS_ORIGINS', ['*'])
        assert 'getattr(settings, "CORS_ORIGINS", ["*"])' not in content, (
            "main.py still has CORS wildcard ['*'] as default"
        )

    def test_cors_none_default(self):
        content = read("backend/api/main.py")
        assert 'getattr(settings, "CORS_ORIGINS", None)' in content, (
            "main.py must use None as default for CORS_ORIGINS"
        )

    def test_production_warning_present(self):
        content = read("backend/api/main.py")
        assert "CORS_ORIGINS not set" in content, (
            "main.py must warn when CORS_ORIGINS not set in production"
        )

    def test_main_py_valid_python(self):
        content = read("backend/api/main.py")
        ast.parse(content)

    def test_main_py_research_registered(self):
        content = read("backend/api/main.py")
        assert "research" in content and "/research" in content, (
            "main.py must register research router (BUG-AC2 must remain fixed)"
        )


# ══ Summary ══════════════════════════════════════════════════════════════════

class TestPhaseADSummary:
    def test_all_admin_files_non_empty(self):
        for path in [
            "backend/api/routes/admin.py",
            "backend/api/routes/admin_observability.py",
            "backend/api/routes/admin_users.py",
            "backend/api/main.py",
        ]:
            content = read(path)
            assert len(content) > 500, f"{path} too small: {len(content)} bytes"

    def test_no_double_prefix_in_any_admin_route(self):
        for path, expected_no_prefix in [
            ("backend/api/routes/admin.py", 'prefix="/admin"'),
            ("backend/api/routes/admin_observability.py", 'prefix="/admin"'),
            ("backend/api/routes/admin_users.py", 'prefix="/admin/users"'),
        ]:
            content = read(path)
            router_lines = [l for l in content.splitlines() if "router = APIRouter" in l]
            for line in router_lines:
                assert expected_no_prefix not in line, (
                    f"{path} still has double prefix: {line}"
                )

    def test_score_100(self):
        """Verify all Phase AD fixes are in place."""
        checks = {
            "admin.py no prefix": 'prefix="/admin"' not in [l for l in read("backend/api/routes/admin.py").splitlines() if "router = APIRouter" in l][0],
            "admin.py get_current_user": "get_current_user" in read("backend/api/routes/admin.py"),
            "obs.py no FakeCtx": "class _FakeCtx" not in read("backend/api/routes/admin_observability.py"),
            "obs.py get_current_user": "get_current_user" in read("backend/api/routes/admin_observability.py"),
            "users.py no /admin/users prefix": 'prefix="/admin/users"' not in read("backend/api/routes/admin_users.py"),
            "main.py CORS None default": 'getattr(settings, "CORS_ORIGINS", None)' in read("backend/api/main.py"),
        }
        failed = [k for k, v in checks.items() if not v]
        assert not failed, f"Phase AD checks failed: {failed}"
