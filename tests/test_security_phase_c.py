"""tests/test_security_phase_c.py

Phase C security test suite — 18 test cases covering:
 - LicenseEngine fail-closed on missing secret
 - HMAC tamper detection
 - Heartbeat concurrent-use detection
 - Config production secret warnings
 - JWT weak-key validator
 - startup_check _check_secrets
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import patch, MagicMock

import pytest


# ── LicenseEngine tests ───────────────────────────────────────────────────

class TestLicenseEngineSecurity:
    """Tests for Phase C security hardening of LicenseEngine."""

    def _make_engine(self, secret: bytes | None = None, replay_window: int = 3600):
        """Create a LicenseEngine with an explicit secret (bypasses Settings)."""
        from backend.license.engine import LicenseEngine
        return LicenseEngine(secret=secret, replay_window=replay_window)

    # SEC-C2: Empty secret -> fail-closed
    def test_validate_with_empty_secret_returns_none(self):
        engine = self._make_engine(secret=b"")
        result = engine.validate("uid:PRO:99999999999.fakesig", user_id="uid")
        assert result is None, "Empty secret must deny validation (fail-closed)"

    def test_issue_with_empty_secret_raises(self):
        engine = self._make_engine(secret=b"")
        with pytest.raises(PermissionError):
            engine.issue("uid", "PRO")

    # SEC-C5: HMAC tamper detection
    def test_tampered_signature_returns_none(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        key = engine.issue("user1", "PRO")
        tampered = key[:-4] + "0000"
        assert engine.validate(tampered, user_id="user1") is None

    def test_tampered_payload_returns_none(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        key = engine.issue("user1", "BASIC")
        # Change BASIC -> ENTERPRISE in payload
        tampered = key.replace(":BASIC:", ":ENTERPRISE:", 1)
        assert engine.validate(tampered, user_id="user1") is None

    def test_wrong_user_id_returns_none(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        key = engine.issue("user1", "PRO")
        assert engine.validate(key, user_id="user2") is None

    def test_valid_key_returns_plan(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        key = engine.issue("user1", "PRO")
        plan = engine.validate(key, user_id="user1")
        assert plan == "PRO"

    def test_expired_key_returns_none(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        key = engine.issue("user1", "PRO", ttl_seconds=-1)  # already expired
        assert engine.validate(key, user_id="user1") is None

    def test_malformed_key_returns_none(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        assert engine.validate("nodot_here", user_id="user1") is None
        assert engine.validate("", user_id="user1") is None

    def test_invalid_plan_in_payload_returns_none(self):
        """Manually forge a key with invalid plan (bypassing issue() validation)."""
        import hashlib, hmac as hmac_mod
        secret = b"test_secret_32_chars_long_exactly"
        expiry = int(time.time()) + 86400
        payload = f"user1:HACKER:{expiry}"
        sig = hmac_mod.new(secret, payload.encode(), hashlib.sha256).hexdigest()
        key = f"{payload}.{sig}"
        engine = self._make_engine(secret=secret)
        assert engine.validate(key, user_id="user1") is None

    # Heartbeat concurrent-use detection
    def test_heartbeat_same_machine_ok(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        assert engine.heartbeat("user1", "machine-A") is True
        assert engine.heartbeat("user1", "machine-A") is True

    def test_heartbeat_different_machine_blocked(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly", replay_window=3600)
        assert engine.heartbeat("user1", "machine-A") is True
        assert engine.heartbeat("user1", "machine-B") is False

    def test_heartbeat_different_machine_after_window_ok(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly", replay_window=1)
        assert engine.heartbeat("user1", "machine-A") is True
        time.sleep(1.1)
        # After replay window, new machine is allowed
        assert engine.heartbeat("user1", "machine-B") is True

    def test_stats_secret_configured_true(self):
        engine = self._make_engine(secret=b"test_secret_32_chars_long_exactly")
        stats = engine.stats()
        assert stats["secret_configured"] is True

    def test_stats_secret_configured_false(self):
        engine = self._make_engine(secret=b"")
        stats = engine.stats()
        assert stats["secret_configured"] is False


# ── Config production warnings ───────────────────────────────────────────

class TestConfigProductionWarnings:
    """Tests for config.py production secret validation."""

    def test_weak_jwt_raises_in_production(self):
        import os
        from pydantic import ValidationError
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with pytest.raises((ValidationError, ValueError)):
                from backend.core.config import Settings
                Settings(JWT_SECRET_KEY="changeme", ENVIRONMENT="production")

    def test_validate_settings_logs_missing_secrets(self, caplog):
        import logging
        from backend.core.config import Settings, validate_settings
        with patch("backend.core.config.is_production", return_value=True):
            with caplog.at_level(logging.ERROR, logger="backend.core.config"):
                s = Settings(
                    ENVIRONMENT="production",
                    JWT_SECRET_KEY="a" * 32,  # strong enough to pass validator
                    LICENSE_SECRET="",
                    FIELD_ENCRYPTION_KEY="",
                )
                validate_settings(s)
        assert any("LICENSE_SECRET" in r.message for r in caplog.records)


# ── Startup check secrets ─────────────────────────────────────────────────

class TestStartupCheckSecrets:
    """Tests for startup_check._check_secrets."""

    @pytest.mark.asyncio
    async def test_check_secrets_not_production_passes(self):
        with patch("backend.startup_check.is_production", return_value=False):
            from backend.startup_check import _check_secrets
            name, ok, msg = await _check_secrets()
            assert ok is True
            assert "skipped" in msg

    @pytest.mark.asyncio
    async def test_check_secrets_production_missing_fails(self):
        mock_settings = MagicMock()
        mock_settings.SECRETS_MASTER_KEY = ""
        mock_settings.FIELD_ENCRYPTION_KEY = ""
        mock_settings.LICENSE_SECRET = ""
        with patch("backend.startup_check.is_production", return_value=True), \
             patch("backend.startup_check.get_settings", return_value=mock_settings):
            from backend.startup_check import _check_secrets
            name, ok, msg = await _check_secrets()
            assert ok is False
            assert "missing" in msg
