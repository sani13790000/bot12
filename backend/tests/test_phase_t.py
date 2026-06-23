"""backend/tests/test_phase_t.py — Phase T tests (T-1..T-30)"""
from __future__ import annotations

import time
from datetime import timezone, datetime
from unittest.mock import MagicMock, patch


# ======================================================
# T-1..T-6 Signals
# ======================================================
class TestSignalsRoute:

    def test_valid_symbol_accepted(self):
        from backend.api.routes.signals_patch import SignalCreateRequest
        r = SignalCreateRequest(symbol="eurusd", direction="buy", score=75.0)
        assert r.symbol == "EURUSD"
        assert r.direction == "BUY"

    def test_invalid_symbol_rejected(self):
        from backend.api.routes.signals_patch import SignalCreateRequest
        from pydantic import ValidationError
        try:
            SignalCreateRequest(symbol="FAKECOIN", direction="BUY", score=50.0)
            assert False, "Should have raised"
        except (ValidationError, ValueError):
            pass

    def test_invalid_direction_rejected(self):
        from backend.api.routes.signals_patch import SignalCreateRequest
        from pydantic import ValidationError
        try:
            SignalCreateRequest(symbol="EURUSD", direction="HOLD", score=50.0)
            assert False
        except (ValidationError, ValueError):
            pass

    def test_score_out_of_range(self):
        from backend.api.routes.signals_patch import SignalCreateRequest
        from pydantic import ValidationError
        try:
            SignalCreateRequest(symbol="EURUSD", direction="BUY", score=150.0)
            assert False
        except (ValidationError, ValueError):
            pass

    def test_ownership_correct_user(self):
        from backend.api.routes.signals_patch import _assert_owns
        _assert_owns({"user_id": "u1"}, "u1")

    def test_ownership_wrong_user_404(self):
        from backend.api.routes.signals_patch import _assert_owns
        from fastapi import HTTPException
        try:
            _assert_owns({"user_id": "u1"}, "u2")
            assert False
        except HTTPException as e:
            assert e.status_code == 404

    def test_ownership_missing_row_404(self):
        from backend.api.routes.signals_patch import _assert_owns
        from fastapi import HTTPException
        try:
            _assert_owns(None, "u1")
            assert False
        except HTTPException as e:
            assert e.status_code == 404

    def test_page_size_max(self):
        from backend.api.routes.signals_patch import _PAGE_SIZE_MAX
        assert _PAGE_SIZE_MAX == 100


# ======================================================
# T-7..T-12 Trades
# ======================================================
class TestTradesRoute:

    def test_ownership_correct_user(self):
        from backend.api.routes.trades_patch import _assert_owns_trade
        _assert_owns_trade({"user_id": "u1"}, "u1")

    def test_ownership_wrong_user_404(self):
        from backend.api.routes.trades_patch import _assert_owns_trade
        from fastapi import HTTPException
        try:
            _assert_owns_trade({"user_id": "u1"}, "u2")
            assert False
        except HTTPException as e:
            assert e.status_code == 404

    def test_closeable_statuses(self):
        from backend.api.routes.trades_patch import _CLOSEABLE_STATUSES
        assert "OPEN" in _CLOSEABLE_STATUSES
        assert "CLOSED" not in _CLOSEABLE_STATUSES

    def test_page_size_max(self):
        from backend.api.routes.trades_patch import _PAGE_SIZE_MAX
        assert _PAGE_SIZE_MAX == 200


# ======================================================
# T-13..T-18 Observability
# ======================================================
class TestObservabilityPatch:

    def test_dedup_suppresses(self):
        from backend.observability.observability_patch import AlertDeduplicator
        d = AlertDeduplicator(60)
        assert d.should_fire("r", {}) is True
        assert d.should_fire("r", {}) is False

    def test_dedup_different_context(self):
        from backend.observability.observability_patch import AlertDeduplicator
        d = AlertDeduplicator(60)
        assert d.should_fire("r", {"a": "1"}) is True
        assert d.should_fire("r", {"a": "2"}) is True

    def test_dedup_reset(self):
        from backend.observability.observability_patch import AlertDeduplicator
        d = AlertDeduplicator(60)
        d.should_fire("r", {})
        d.reset()
        assert d.should_fire("r", {}) is True

    def test_latency_histogram(self):
        from backend.observability.observability_patch import TradeLatencyHistogram
        h = TradeLatencyHistogram()
        for v in range(1, 101):
            h.observe_sync(float(v))
        snap = h.snapshot()
        assert snap["count"] == 100
        assert snap["p99_ms"] >= snap["p50_ms"]

    def test_prometheus_fallback(self):
        from backend.observability.observability_patch import get_prometheus_text
        text = get_prometheus_text()
        assert isinstance(text, str) and len(text) > 0

    def test_correlation_id(self):
        from backend.observability.observability_patch import set_correlation_id, get_correlation_id
        set_correlation_id("test-cid")
        assert get_correlation_id() == "test-cid"

    def test_safe_label_key(self):
        from backend.observability.observability_patch import safe_label_key
        k = safe_label_key(method="GET", path="/x", status="200")
        assert k == safe_label_key(status="200", method="GET", path="/x")


# ======================================================
# T-19..T-24 RBAC
# ======================================================
class TestRBACPatch:

    def test_cache_set_get(self):
        from backend.services.rbac_patch import ProactivePermCache
        c = ProactivePermCache()
        c.set("u1:T", True)
        assert c.get("u1:T") is True

    def test_cache_miss(self):
        from backend.services.rbac_patch import ProactivePermCache
        assert ProactivePermCache().get("x:y") is None

    def test_cache_expired(self):
        from backend.services.rbac_patch import ProactivePermCache
        c = ProactivePermCache(ttl=60)
        c.set("u1:T", True)
        for k in c._store:
            c._store[k] = (c._store[k][0], datetime(2000, 1, 1, tzinfo=timezone.utc))
        assert c.get("u1:T") is None

    def test_wildcard_expansion(self):
        from backend.services.rbac_patch import expand_wildcard_permissions
        rp = {"a": {"R", "D", "*"}}
        exp = expand_wildcard_permissions({"*"}, rp)
        assert "*" not in exp and "D" in exp

    def test_rate_limiter_blocks(self):
        from backend.services.rbac_patch import PermissionCheckRateLimiter
        rl = PermissionCheckRateLimiter()
        rl._MAX_CALLS = 2
        rl.is_allowed("u"); rl.is_allowed("u")
        assert rl.is_allowed("u") is False


# ======================================================
# T-25..T-30 Config
# ======================================================
class TestConfigPatch:

    def _ms(self, **kw):
        d = dict(JWT_SECRET_KEY="a" * 32, SUPABASE_URL="https://x.y", ACCESS_TOKEN_EXPIRE_MINUTES=30, CORS_ORIGINS=["https://x.com"], BCRYPT_ROUNDS=12)
        d.update(kw); s = MagicMock()
        for k, v in d.items(): setattr(s, k, v)
        return s

    def test_valid_settings(self):
        from backend.core.config_patch import validate_settings
        with patch("backend.core.config_patch._detect_environment", return_value="development"):
            validate_settings(self._ms())

    def test_dangerous_key_in_prod(self):
        from backend.core.config_patch import validate_settings
        with patch("backend.core.config_patch._detect_environment", return_value="production"):
            try:
                validate_settings(self._ms(JWT_SECRET_KEY="changeme"))
                assert False
            except RuntimeError as e:
                assert "JWT" in str(e)

    def test_short_key_raises(self):
        from backend.core.config_patch import validate_settings
        with patch("backend.core.config_patch._detect_environment", return_value="development"):
            try:
                validate_settings(self._ms(JWT_SECRET_KEY="short"))
                assert False
            except RuntimeError:
                pass

    def test_wildcard_cors_in_prod(self):
        from backend.core.config_patch import validate_settings
        with patch("backend.core.config_patch._detect_environment", return_value="production"):
            try:
                validate_settings(self._ms(CORS_ORIGINS=["*"]))
                assert False
            except RuntimeError as e:
                assert "CORS" in str(e)

    def test_env_detection(self):
        import os
        from backend.core.config_patch import _detect_environment
        os.environ["APP_ENV"] = "production"
        assert _detect_environment() == "production"
        del os.environ["APP_ENV"]
        assert _detect_environment() == "development"
