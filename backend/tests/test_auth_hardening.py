"""backend/tests/test_auth_hardening.py — 15 tests for all 11 fixes."""
from __future__ import annotations
import asyncio
import re
import time
from unittest.mock import MagicMock, patch
import pytest


class TestDummyHash:
    def test_dummy_hash_length(self):
        from backend.api.routes.auth import _DUMMY_HASH
        assert len(_DUMMY_HASH) == 60

    def test_dummy_hash_prefix(self):
        from backend.api.routes.auth import _DUMMY_HASH
        assert _DUMMY_HASH.startswith("$2b$12$")

    def test_safe_verify_wrong_password(self):
        from backend.api.routes.auth import _DUMMY_HASH, _safe_verify
        assert _safe_verify("wrong", _DUMMY_HASH) is False

    def test_safe_verify_malformed_returns_false(self):
        from backend.api.routes.auth import _safe_verify
        assert _safe_verify("any", "$2b$12$notarealhashjustpadding") is False

    def test_safe_verify_empty(self):
        from backend.api.routes.auth import _safe_verify
        assert _safe_verify("", "somehash") is False
        assert _safe_verify("pw", "") is False


class TestLockout:
    def test_lockout_after_5_failures(self):
        import backend.api.routes.auth as m
        m._attempts.clear()
        m._lockout_until.clear()
        loop = asyncio.new_event_loop()
        ip = "10.1.2.3"
        for _ in range(5):
            loop.run_until_complete(m._record_failure(ip))
        assert loop.run_until_complete(m._is_locked(ip)) is True
        loop.close()

    def test_deque_capped_at_5(self):
        from backend.api.routes.auth import _attempts, _LOCKOUT_MAX_ATTEMPTS
        _attempts.clear()
        ip = "192.168.1.50"
        dq = _attempts[ip]
        for i in range(20):
            dq.append(time.monotonic())
        assert len(dq) <= _LOCKOUT_MAX_ATTEMPTS


class TestIPExtraction:
    def test_login_uses_get_client_ip(self):
        import inspect
        import backend.api.routes.auth as m
        src = inspect.getsource(m.login)
        assert "get_client_ip(request)" in src
        assert "request.client.host" not in src


class TestJWT:
    def _mock_settings(self):
        return MagicMock(
            JWT_SECRET_KEY="x" * 32,
            ACCESS_TOKEN_EXPIRE_MINUTES=30,
            REFRESH_TOKEN_EXPIRE_DAYS=30,
        )

    def test_access_token_type(self):
        with patch("backend.core.security.get_settings", return_value=self._mock_settings()):
            from backend.core.security import create_access_token, validate_access_token
            token = create_access_token("u1")
            p = validate_access_token(token)
            assert p["type"] == "access" and p["sub"] == "u1"

    def test_reserved_claims_not_overridable(self):
        with patch("backend.core.security.get_settings", return_value=self._mock_settings()):
            from backend.core.security import create_access_token, decode_token
            token = create_access_token("u2", extra_claims={"sub": "INJECTED", "type": "admin"})
            p = decode_token(token)
            assert p["sub"] == "u2"
            assert p["type"] == "access"

    def test_jti_is_64_hex_chars(self):
        with patch("backend.core.security.get_settings", return_value=self._mock_settings()):
            from backend.core.security import create_access_token, decode_token
            token = create_access_token("u3")
            p = decode_token(token)
            assert re.match(r"^[0-9a-f]{64}$", p["jti"])


class TestVerifyPassword:
    def test_malformed_returns_false(self):
        from backend.core.security import verify_password
        assert verify_password("pw", "not-a-hash") is False

    def test_empty_returns_false(self):
        from backend.core.security import verify_password
        assert verify_password("", "h") is False
        assert verify_password("p", "") is False


class TestHMAC:
    def test_empty_secret_raises(self):
        from backend.core.security import sign_payload
        with pytest.raises(ValueError):
            sign_payload(b"data", "")

    def test_empty_secret_verify_false(self):
        from backend.core.security import verify_signature
        assert verify_signature(b"data", "", "anysig") is False


class TestHashPassword:
    def test_72_byte_limit(self):
        from backend.core.security import hash_password
        with pytest.raises(ValueError, match="too long"):
            hash_password("A" * 73)
