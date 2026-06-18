"""
Phase 10 — Security Test Suite
50 tests: SQL injection, XSS, path traversal, JWT, license, secrets
"""
from __future__ import annotations

import pytest
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock


# ============================================================
# SecurityMiddleware Tests
# ============================================================
class TestSQLInjectionDetection:
    def setup_method(self):
        from backend.middleware.security import _check_sql, _scan_value
        self._check_sql = _check_sql
        self._scan_value = _scan_value

    def test_select_statement_blocked(self):
        assert self._check_sql("SELECT * FROM users") is True

    def test_drop_table_blocked(self):
        assert self._check_sql("DROP TABLE trades") is True

    def test_union_blocked(self):
        assert self._check_sql("1 UNION SELECT password FROM users") is True

    def test_comment_blocked(self):
        assert self._check_sql("admin'--") is True

    def test_or_injection_blocked(self):
        assert self._check_sql("OR 1=1") is True

    def test_normal_text_allowed(self):
        assert self._check_sql("XAUUSD analysis report") is False

    def test_price_value_allowed(self):
        assert self._check_sql("1950.50") is False

    def test_nested_dict_scan(self):
        payload = {"user": {"name": "SELECT * FROM users"}}
        assert self._scan_value(payload) == "sql_injection"

    def test_nested_list_scan(self):
        payload = ["normal", "DROP TABLE trades"]
        assert self._scan_value(payload) == "sql_injection"

    def test_clean_payload_passes(self):
        payload = {"symbol": "XAUUSD", "timeframe": "H1", "risk": 1.0}
        assert self._scan_value(payload) is None


class TestXSSDetection:
    def setup_method(self):
        from backend.middleware.security import _check_xss, _scan_value
        self._check_xss = _check_xss
        self._scan_value = _scan_value

    def test_script_tag_blocked(self):
        assert self._check_xss("<script>alert('xss')</script>") is True

    def test_javascript_protocol_blocked(self):
        assert self._check_xss("javascript:alert(1)") is True

    def test_onclick_blocked(self):
        assert self._check_xss("<div onclick=alert(1)>") is True

    def test_iframe_blocked(self):
        assert self._check_xss("<iframe src='evil.com'>") is True

    def test_eval_blocked(self):
        assert self._check_xss("eval(atob('YWxlcnQ='))") is True

    def test_normal_html_description_allowed(self):
        assert self._check_xss("Gold price analysis for today") is False

    def test_xss_in_nested_value(self):
        payload = {"comment": "<script>steal()</script>"}
        assert self._scan_value(payload) == "xss"


class TestPathTraversalDetection:
    def setup_method(self):
        from backend.middleware.security import _PATH_TRAVERSAL, _scan_value
        self._pat = _PATH_TRAVERSAL
        self._scan_value = _scan_value

    def test_dotdot_slash_blocked(self):
        assert self._pat.search("../../etc/passwd") is not None

    def test_encoded_traversal_blocked(self):
        assert self._pat.search("%2e%2e/etc/passwd") is not None

    def test_double_encoded_blocked(self):
        assert self._pat.search("%252e%252e") is not None

    def test_normal_path_allowed(self):
        assert self._pat.search("/api/v1/signals") is None

    def test_traversal_in_value(self):
        assert self._scan_value("../../etc/shadow") == "path_traversal"


# ============================================================
# JWT Auth Tests
# ============================================================
class TestJWTAuth:
    def setup_method(self):
        from backend.core.auth import TokenPayload, _parse_supabase_jwt
        self.TokenPayload = TokenPayload
        self._parse_supabase_jwt = _parse_supabase_jwt

    def _make_token(self, payload: dict) -> str:
        import base64
        import json
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
        body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"{header}.{body}.fakesig"

    def test_valid_token_parsed(self):
        token = self._make_token({
            "sub": "user-123",
            "email": "test@example.com",
            "role": "authenticated",
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        })
        result = self._parse_supabase_jwt(token)
        assert result is not None
        assert result.user_id == "user-123"
        assert result.email == "test@example.com"

    def test_expired_token_detected(self):
        token = self._make_token({
            "sub": "user-123",
            "email": "test@example.com",
            "exp": int(time.time()) - 100,
            "iat": int(time.time()) - 3700,
        })
        result = self._parse_supabase_jwt(token)
        assert result is not None
        assert result.is_expired is True

    def test_admin_role_detected(self):
        token = self._make_token({
            "sub": "admin-1",
            "email": "admin@example.com",
            "exp": int(time.time()) + 3600,
            "app_metadata": {"role": "admin"},
        })
        result = self._parse_supabase_jwt(token)
        assert result is not None
        assert result.is_admin is True

    def test_missing_sub_returns_empty_user_id(self):
        token = self._make_token({
            "email": "test@example.com",
            "exp": int(time.time()) + 3600,
        })
        result = self._parse_supabase_jwt(token)
        assert result is not None
        assert result.user_id == ""

    def test_invalid_token_returns_none(self):
        result = self._parse_supabase_jwt("not.a.valid.jwt.token")
        assert result is None

    def test_token_payload_has_scope(self):
        payload = self.TokenPayload(
            user_id="u1",
            email="u@example.com",
            scopes=["signals_read", "research"],
        )
        assert payload.has_scope("signals_read") is True
        assert payload.has_scope("mt5") is False

    def test_admin_has_all_scopes(self):
        payload = self.TokenPayload(
            user_id="admin",
            email="admin@example.com",
            role="admin",
        )
        assert payload.has_scope("mt5") is True
        assert payload.has_scope("any_scope") is True


# ============================================================
# License Manager Tests
# ============================================================
class TestLicenseManager:
    def setup_method(self):
        from backend.core.license_manager import (
            get_plan_limits, check_signal_limit, record_signal_usage,
            check_backtest_limit, check_feature_access, get_usage_summary,
            PlanTier
        )
        self.get_plan_limits = get_plan_limits
        self.check_signal_limit = check_signal_limit
        self.record_signal_usage = record_signal_usage
        self.check_backtest_limit = check_backtest_limit
        self.check_feature_access = check_feature_access
        self.get_usage_summary = get_usage_summary
        self.PlanTier = PlanTier

    def test_free_plan_signal_limit(self):
        limits = self.get_plan_limits("free")
        assert limits.max_signals_per_day == 5

    def test_pro_plan_has_ml(self):
        limits = self.get_plan_limits("pro")
        assert limits.can_use_ml is True

    def test_free_plan_no_ml(self):
        limits = self.get_plan_limits("free")
        assert limits.can_use_ml is False

    def test_enterprise_has_mt5(self):
        limits = self.get_plan_limits("enterprise")
        assert limits.can_use_mt5 is True

    def test_signal_limit_enforced(self):
        user_id = f"test-user-limit-{time.time()}"
        limits = self.get_plan_limits("free")
        for _ in range(limits.max_signals_per_day):
            assert self.check_signal_limit(user_id, "free") is True
            self.record_signal_usage(user_id)
        assert self.check_signal_limit(user_id, "free") is False

    def test_pro_feature_access(self):
        assert self.check_feature_access("pro", "ml") is True
        assert self.check_feature_access("pro", "mt5") is True

    def test_free_feature_denied(self):
        assert self.check_feature_access("free", "ml") is False
        assert self.check_feature_access("free", "mt5") is False

    def test_usage_summary_has_required_keys(self):
        summary = self.get_usage_summary("summary-user", "basic")
        assert "tier" in summary
        assert "signals_used" in summary
        assert "signals_limit" in summary
        assert "backtests_used" in summary
        assert "backtests_limit" in summary

    def test_unknown_tier_defaults_to_free(self):
        limits = self.get_plan_limits("unknown_tier")
        assert limits.tier == self.PlanTier.FREE


# ============================================================
# Secret Manager Tests
# ============================================================
class TestSecretManager:
    def test_validate_secrets_returns_result(self):
        from backend.middleware.secret_manager import validate_secrets
        result = validate_secrets()
        assert hasattr(result, "ok")
        assert hasattr(result, "missing_required")
        assert hasattr(result, "summary")

    def test_get_secret_returns_default(self):
        from backend.middleware.secret_manager import get_secret
        val = get_secret("NONEXISTENT_SECRET_XYZ", "default_value")
        assert val == "default_value"

    def test_get_secret_returns_env_value(self, monkeypatch):
        from backend.middleware.secret_manager import get_secret
        monkeypatch.setenv("TEST_SECRET_PHASE10", "my_secret_value")
        val = get_secret("TEST_SECRET_PHASE10")
        assert val == "my_secret_value"

    def test_summary_has_valid_key(self):
        from backend.middleware.secret_manager import validate_secrets
        result = validate_secrets()
        summary = result.summary()
        assert "valid" in summary
        assert "missing_required" in summary
