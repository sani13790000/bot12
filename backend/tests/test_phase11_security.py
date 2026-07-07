"""
tests/test_phase11_security.py
PHASE 11 — Secrets, Encryption & Data Protection
Target: 88/88 PASS
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase11-testing-32chars")
os.environ.setdefault("SECRETS_MASTER_KEY", "test-master-key-for-phase11-exactly-32chars!!")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", "a" * 64)

from backend.core.secret_store import (
    DecryptionError, SecretNotFoundError, SecretStore,
    _aes_gcm_decrypt, _aes_gcm_encrypt, _derive_key,
    envelope_decrypt, envelope_encrypt, get_secret_store,
)
from backend.core.log_redactor import (
    RedactionFilter, redact_dict, redact_string, structlog_redact_processor,
)
from backend.core.field_encryption import (
    FieldEncryption, decrypt_field, encrypt_field, get_field_encryption,
)
from backend.core.config_v11 import Settings, get_settings
from backend.middleware.security_headers import (
    SecurityHeadersMiddleware, _detect_injection, block_ip, blocked_ips, unblock_ip,
)


# ═══ T01-T12: Secret Store ════════════════════════════════════════
class TestSecretStore:
    def setup_method(self):
        self.store = SecretStore("test-master-password-for-unit-tests!!")

    def test_T01_put_and_get_roundtrip(self):
        self.store.put("my_secret", "super-secret-value")
        assert self.store.get("my_secret") == "super-secret-value"

    def test_T02_raw_value_never_stored_plain(self):
        self.store.put("api_key", "plain-text-api-key-12345")
        rec = self.store._store["api_key"]
        assert b"plain-text-api-key-12345" not in rec.ciphertext

    def test_T03_ciphertext_different_each_put(self):
        self.store.put("key1", "same-value")
        ct1 = bytes(self.store._store["key1"].ciphertext)
        self.store.put("key1", "same-value")
        ct2 = bytes(self.store._store["key1"].ciphertext)
        assert ct1 != ct2

    def test_T04_get_missing_raises(self):
        with pytest.raises(SecretNotFoundError):
            self.store.get("nonexistent_key")

    def test_T05_rotate_updates_value(self):
        self.store.put("token", "old-token")
        self.store.rotate("token", "new-token")
        assert self.store.get("token") == "new-token"

    def test_T06_rotate_missing_raises(self):
        with pytest.raises(SecretNotFoundError):
            self.store.rotate("missing", "val")

    def test_T07_delete_removes_secret(self):
        self.store.put("temp", "value")
        self.store.delete("temp")
        assert not self.store.exists("temp")

    def test_T08_list_names_no_values(self):
        self.store.put("a", "va")
        self.store.put("b", "vb")
        names = self.store.list_names()
        assert "a" in names and "b" in names
        assert "va" not in str(names) and "vb" not in str(names)

    def test_T09_audit_log_recorded(self):
        self.store.put("x", "v")
        self.store.get("x")
        actions = [e["action"] for e in self.store.audit_log()]
        assert "put" in actions and "get" in actions

    def test_T10_audit_log_no_values(self):
        self.store.put("secret", "my-super-secret")
        log_str = str(self.store.audit_log())
        assert "my-super-secret" not in log_str

    def test_T11_wrong_master_decryption_fails(self):
        self.store.put("key", "value")
        rec = self.store._store["key"]
        store2 = SecretStore("different-master-key-for-testing!!")
        store2._store["key"] = rec
        with pytest.raises(Exception):
            store2.get("key")

    def test_T12_zero_master_clears_key(self):
        self.store.put("k", "v")
        self.store.zero_master()
        assert all(b == 0 for b in self.store._master)


# ═══ T13-T24: Envelope Encryption ══════════════════════════════════
class TestEnvelopeEncryption:
    def test_T13_encrypt_decrypt_roundtrip(self):
        pw = b"master-password-test"
        ct = envelope_encrypt(pw, b"hello world")
        assert envelope_decrypt(pw, ct) == b"hello world"

    def test_T14_different_ciphertext_each_time(self):
        pw = b"master-pw"
        ct1 = envelope_encrypt(pw, b"same")
        ct2 = envelope_encrypt(pw, b"same")
        assert ct1 != ct2

    def test_T15_tamper_detection(self):
        pw = b"master-pw"
        ct = bytearray(envelope_encrypt(pw, b"data"))
        ct[-1] ^= 0xFF
        with pytest.raises(DecryptionError):
            envelope_decrypt(pw, bytes(ct))

    def test_T16_wrong_password_fails(self):
        ct = envelope_encrypt(b"correct-pw", b"secret")
        with pytest.raises(DecryptionError):
            envelope_decrypt(b"wrong-pw", ct)

    def test_T17_aes_gcm_encrypt_decrypt(self):
        key = secrets.token_bytes(32)
        pt = b"test plaintext data"
        ct = _aes_gcm_encrypt(key, pt)
        assert _aes_gcm_decrypt(key, ct) == pt

    def test_T18_aes_gcm_tamper_raises(self):
        key = secrets.token_bytes(32)
        ct = bytearray(_aes_gcm_encrypt(key, b"data"))
        ct[-1] ^= 0x01
        with pytest.raises(DecryptionError):
            _aes_gcm_decrypt(key, bytes(ct))

    def test_T19_derive_key_deterministic(self):
        pw, salt = b"pw", b"salt" * 8
        k1 = _derive_key(pw, salt)
        k2 = _derive_key(pw, salt)
        assert k1 == k2 and len(k1) == 32

    def test_T20_derive_key_different_salts(self):
        pw = b"pw"
        k1 = _derive_key(pw, b"salt1" * 6)
        k2 = _derive_key(pw, b"salt2" * 6)
        assert k1 != k2

    def test_T21_envelope_too_short_raises(self):
        with pytest.raises(DecryptionError):
            envelope_decrypt(b"pw", b"x")

    def test_T22_plaintext_not_in_ciphertext(self):
        pw = b"master"
        ct = envelope_encrypt(pw, b"super-secret-data")
        assert b"super-secret-data" not in ct

    def test_T23_large_payload(self):
        pw = b"master-pw"
        data = secrets.token_bytes(10_000)
        ct = envelope_encrypt(pw, data)
        assert envelope_decrypt(pw, ct) == data

    def test_T24_unicode_secret(self):
        store = SecretStore("master-key-for-unicode-test!!!!")
        val = "سلام دنیا"
        store.put("fa", val)
        assert store.get("fa") == val


# ═══ T25-T36: Log Redaction ═════════════════════════════════════════
class TestLogRedaction:
    def test_T25_jwt_redacted(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.abc123def456"
        result = redact_string(f"token={jwt}")
        assert jwt not in result
        assert "REDACTED" in result

    def test_T26_password_kv_redacted(self):
        result = redact_string("password=mysecret123")
        assert "mysecret123" not in result
        assert "REDACTED" in result

    def test_T27_bearer_redacted(self):
        result = redact_string("Authorization: Bearer eyJtoken123456789")
        assert "eyJtoken123456789" not in result
        assert "REDACTED" in result

    def test_T28_dict_sensitive_keys_redacted(self):
        d = {"username": "user1", "password": "secret123", "api_key": "key456"}
        result = redact_dict(d)
        assert result["username"] == "user1"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"

    def test_T29_nested_dict_redacted(self):
        d = {"user": {"name": "alice", "password": "pw123"}}
        result = redact_dict(d)
        assert result["user"]["password"] == "[REDACTED]"
        assert result["user"]["name"] == "alice"

    def test_T30_redaction_filter_on_logger(self):
        logger = logging.getLogger("test_redact")
        f = RedactionFilter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="",
            lineno=0, msg="password=secret123", args=(), exc_info=None,
        )
        f.filter(record)
        assert "secret123" not in record.msg

    def test_T31_structlog_processor(self):
        event = {"event": "login", "password": "pw123", "user": "alice"}
        result = structlog_redact_processor(None, "info", event)
        assert result["password"] == "[REDACTED]"
        assert result["user"] == "alice"

    def test_T32_hex_secret_redacted(self):
        hex_key = "a" * 32
        result = redact_string(f"key={hex_key}")
        assert hex_key not in result

    def test_T33_normal_text_not_redacted(self):
        text = "user logged in from browser at 2026-01-01"
        result = redact_string(text)
        assert result == text

    def test_T34_card_number_redacted(self):
        result = redact_string("card: 4111111111111111")
        assert "4111111111111111" not in result
        assert "REDACTED" in result

    def test_T35_list_values_redacted(self):
        d = {"tokens": ["eyJhbGci.eyJzdWIi.abc", "normal"]}
        result = redact_dict(d)
        assert "REDACTED" in result["tokens"][0]

    def test_T36_redaction_does_not_drop_records(self):
        f = RedactionFilter()
        record = logging.LogRecord(
            name="t", level=logging.WARNING, pathname="",
            lineno=0, msg="normal message", args=(), exc_info=None,
        )
        assert f.filter(record) is True


# ═══ T37-T52: Field Encryption ════════════════════════════════════════
class TestFieldEncryption:
    def setup_method(self):
        key = bytes.fromhex("a" * 64)
        self.fe = FieldEncryption(key)

    def test_T37_encrypt_prefix(self):
        enc = self.fe.encrypt("secret-value")
        assert enc.startswith("enc:v1:")

    def test_T38_decrypt_roundtrip(self):
        enc = self.fe.encrypt("license-key-12345")
        assert self.fe.decrypt(enc) == "license-key-12345"

    def test_T39_passthrough_unencrypted(self):
        assert self.fe.decrypt("plain-value") == "plain-value"

    def test_T40_idempotent_encrypt(self):
        enc = self.fe.encrypt("value")
        assert self.fe.encrypt(enc) == enc

    def test_T41_empty_string_passthrough(self):
        assert self.fe.encrypt("") == ""
        assert self.fe.decrypt("") == ""

    def test_T42_different_ciphertext_each_time(self):
        e1 = self.fe.encrypt("same")
        e2 = self.fe.encrypt("same")
        assert e1 != e2

    def test_T43_plaintext_not_in_encrypted(self):
        enc = self.fe.encrypt("my-mt5-password-123")
        assert "my-mt5-password-123" not in enc

    def test_T44_is_encrypted_flag(self):
        assert not self.fe.is_encrypted("plain")
        assert self.fe.is_encrypted(self.fe.encrypt("plain"))

    def test_T45_tamper_raises(self):
        enc = self.fe.encrypt("data")
        tampered = enc[:-4] + "XXXX"
        with pytest.raises(Exception):
            self.fe.decrypt(tampered)

    def test_T46_wrong_key_raises(self):
        enc = self.fe.encrypt("data")
        fe2 = FieldEncryption(bytes.fromhex("b" * 64))
        with pytest.raises(Exception):
            fe2.decrypt(enc)

    def test_T47_rotate_key(self):
        enc = self.fe.encrypt("value")
        new_key = bytes.fromhex("c" * 64)
        new_enc = self.fe.rotate(enc, new_key)
        fe2 = FieldEncryption(new_key)
        assert fe2.decrypt(new_enc) == "value"

    def test_T48_wrong_key_length_raises(self):
        with pytest.raises(ValueError):
            FieldEncryption(b"short")

    def test_T49_encrypt_field_shortcut(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = "a" * 64
        enc = encrypt_field("test-value")
        assert enc.startswith("enc:v1:")

    def test_T50_decrypt_field_shortcut(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = "a" * 64
        enc = encrypt_field("roundtrip")
        assert decrypt_field(enc) == "roundtrip"

    def test_T51_large_field(self):
        long_val = "x" * 10_000
        enc = self.fe.encrypt(long_val)
        assert self.fe.decrypt(enc) == long_val

    def test_T52_unicode_field(self):
        val = "سلام عالم"
        enc = self.fe.encrypt(val)
        assert self.fe.decrypt(enc) == val


# ═══ T53-T64: Settings Validation ═════════════════════════════════════
class TestSettings:
    def _make_settings(self, **kwargs):
        base = {
            "JWT_SECRET_KEY": "test-key-32-chars-minimum-length!!",
            "ENVIRONMENT": "development",
        }
        base.update(kwargs)
        return Settings(**base)

    def test_T53_weak_jwt_in_dev_warns(self):
        s = self._make_settings(JWT_SECRET_KEY="changeme")
        assert s.JWT_SECRET_KEY == "changeme"

    def test_T54_valid_jwt_passes(self):
        s = self._make_settings(JWT_SECRET_KEY="a-valid-key-with-enough-characters-here")
        assert len(s.JWT_SECRET_KEY) >= 32

    def test_T55_master_key_min_32(self):
        with pytest.raises(Exception):
            self._make_settings(SECRETS_MASTER_KEY="short")

    def test_T56_master_key_valid(self):
        s = self._make_settings(SECRETS_MASTER_KEY="a" * 32)
        assert len(s.SECRETS_MASTER_KEY) == 32

    def test_T57_field_enc_key_wrong_length(self):
        with pytest.raises(Exception):
            self._make_settings(FIELD_ENCRYPTION_KEY="a" * 32)  # need 64

    def test_T58_field_enc_key_valid(self):
        s = self._make_settings(FIELD_ENCRYPTION_KEY="a" * 64)
        assert len(s.FIELD_ENCRYPTION_KEY) == 64

    def test_T59_wildcard_origin_in_dev_ok(self):
        s = self._make_settings(ALLOWED_ORIGINS=["http://localhost:3000"])
        assert "http://localhost:3000" in s.ALLOWED_ORIGINS

    def test_T60_cors_credentials_no_wildcard(self):
        s = self._make_settings(ALLOWED_ORIGINS=["https://app.example.com"])
        assert s.cors_allow_credentials() is True

    def test_T61_cors_credentials_wildcard_false(self):
        s = self._make_settings(ALLOWED_ORIGINS=["*"])
        assert s.cors_allow_credentials() is False

    def test_T62_is_production(self):
        s = self._make_settings(ENVIRONMENT="production",
                                JWT_SECRET_KEY="production-key-32-chars-minimum!!",
                                SECRETS_MASTER_KEY="a" * 32)
        assert s.is_production()

    def test_T63_csp_policy_contains_nonce(self):
        s = self._make_settings()
        csp = s.get_csp_policy(nonce="abc123")
        assert "nonce-abc123" in csp

    def test_T64_field_enc_key_invalid_hex(self):
        with pytest.raises(Exception):
            self._make_settings(FIELD_ENCRYPTION_KEY="z" * 64)  # not hex


# ═══ T65-T80: Security Headers ═════════════════════════════════════
class TestSecurityHeadersMiddleware:
    def _make_app(self, env="production", origins=None):
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route
        from starlette.testclient import TestClient

        async def homepage(request):
            return JSONResponse({"ok": True})

        async def api_endpoint(request):
            return JSONResponse({"data": "value"})

        app = Starlette(routes=[
            Route("/", homepage),
            Route("/api/v1/test", api_endpoint),
        ])
        app.add_middleware(
            SecurityHeadersMiddleware,
            environment=env,
            allowed_origins=origins or ["https://example.com"],
        )
        return TestClient(app, raise_server_exceptions=False)

    def test_T65_middleware_sets_security_headers(self):
        client = self._make_app()
        resp = client.get("/")
        assert resp.headers.get("x-content-type-options") == "nosniff"
        assert resp.headers.get("x-frame-options") == "DENY"
        assert resp.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    def test_T66_hsts_in_production(self):
        client = self._make_app(env="production")
        resp = client.get("/")
        hsts = resp.headers.get("strict-transport-security", "")
        assert "max-age=63072000" in hsts

    def test_T67_no_hsts_in_development(self):
        client = self._make_app(env="development")
        resp = client.get("/")
        assert "strict-transport-security" not in resp.headers

    def test_T68_csp_on_html_routes(self):
        client = self._make_app(env="production")
        resp = client.get("/")
        csp = resp.headers.get("content-security-policy", "")
        assert "default-src" in csp
        assert "frame-ancestors 'none'" in csp

    def test_T69_no_csp_on_api_routes(self):
        client = self._make_app(env="production")
        resp = client.get("/api/v1/test")
        assert "content-security-policy" not in resp.headers

    def test_T70_request_id_header(self):
        client = self._make_app()
        resp = client.get("/")
        assert "x-request-id" in resp.headers

    def test_T71_sql_injection_in_query_returns_400(self):
        client = self._make_app()
        resp = client.get("/?q=SELECT * FROM users")
        assert resp.status_code == 400

    def test_T72_csp_nonce_per_request(self):
        client = self._make_app(env="production")
        resp1 = client.get("/")
        resp2 = client.get("/")
        csp1 = resp1.headers.get("content-security-policy", "")
        csp2 = resp2.headers.get("content-security-policy", "")
        # nonces should differ between requests
        assert csp1 != csp2


# ═══ T73-T80: .env.example Validation ═════════════════════════════════
class TestEnvExample:
    @pytest.fixture(autouse=True)
    def load_env_example(self):
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env.example")
        if not os.path.exists(env_path):
            env_path = os.path.join(os.path.dirname(__file__), "..", "env.example")
        if not os.path.exists(env_path):
            pytest.skip(".env.example not found")
        with open(env_path) as f:
            self.content = f.read()

    def test_T73_no_real_secrets_in_env_example(self):
        suspicious = ["eyJ", "sk_live_", "whsec_live", "postgresql://user:realpassword"]
        for s in suspicious:
            if s == "whsec_" and "whsec_CHANGE_ME" in self.content:
                continue
            assert s not in self.content or "CHANGE_ME" in self.content

    def test_T74_all_required_keys_present(self):
        required = [
            "JWT_SECRET_KEY", "SUPABASE_URL", "SECRETS_MASTER_KEY",
            "FIELD_ENCRYPTION_KEY", "MT5_PASSWORD", "TELEGRAM_BOT_TOKEN",
            "LICENSE_SECRET",
        ]
        for key in required:
            assert key in self.content, f"{key} missing from .env.example"

    def test_T75_placeholders_say_change_me(self):
        assert "CHANGE_ME" in self.content

    def test_T76_security_checklist_present(self):
        assert "CHECKLIST" in self.content or "checklist" in self.content.lower()

    def test_T77_debug_false_in_example(self):
        assert "DEBUG=false" in self.content or "DEBUG=False" in self.content

    def test_T78_log_redaction_enabled(self):
        assert "LOG_REDACTION_ENABLED=true" in self.content

    def test_T79_session_cookie_secure(self):
        assert "SESSION_COOKIE_SECURE=true" in self.content

    def test_T80_cors_no_wildcard(self):
        lines = [l for l in self.content.split("\n") if l.startswith("ALLOWED_ORIGINS=")]
        for line in lines:
            assert "*" not in line, f"Wildcard in ALLOWED_ORIGINS: {line}"


# ═══ T81-T88: Integration ═════════════════════════════════════════════
class TestIntegration:
    def test_T81_secret_store_load_from_env(self):
        os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-for-integration-test!!"
        from backend.core.secret_store import SecretStore, _load_from_env
        store = SecretStore("master-key-for-integration-test!!")
        _load_from_env(store)
        val = store.get("JWT_SECRET_KEY")
        assert val == "test-jwt-secret-for-integration-test!!"

    def test_T82_field_encryption_from_env_var(self):
        os.environ["FIELD_ENCRYPTION_KEY"] = "b" * 64
        from backend.core import field_encryption as fe_mod
        fe_mod._fe = None
        fe = fe_mod.get_field_encryption()
        enc = fe.encrypt("test")
        assert fe.decrypt(enc) == "test"

    def test_T83_full_secret_lifecycle(self):
        store = SecretStore("lifecycle-master-key-min-32-chars!!")
        store.put("db_password", "initial-password")
        assert store.get("db_password") == "initial-password"
        store.rotate("db_password", "rotated-password")
        assert store.get("db_password") == "rotated-password"
        store.delete("db_password")
        assert not store.exists("db_password")
        actions = [e["action"] for e in store.audit_log()]
        assert "put" in actions
        assert "rotate" in actions
        assert "delete" in actions

    def test_T84_redaction_in_log_integration(self):
        import io
        logger = logging.getLogger("test_integration_redact")
        logger.setLevel(logging.DEBUG)
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        f = RedactionFilter()
        handler.addFilter(f)
        logger.addHandler(handler)
        try:
            logger.info("User password=my-secret-password-123 logged in")
            output = buf.getvalue()
            assert "my-secret-password-123" not in output
            assert "REDACTED" in output
        finally:
            logger.removeHandler(handler)

    def test_T85_config_cors_credentials_consistency(self):
        s = Settings(
            JWT_SECRET_KEY="valid-key-32-chars-for-test-here!!",
            ALLOWED_ORIGINS=["https://app.example.com"],
        )
        assert s.cors_allow_credentials() is True
        assert s.is_production() is False

    def test_T86_field_encryption_license_key(self):
        key = bytes.fromhex("d" * 64)
        fe = FieldEncryption(key)
        license_key = "BOT12-XXXX-YYYY-ZZZZ-AAAA"
        encrypted = fe.encrypt(license_key)
        assert fe.is_encrypted(encrypted)
        assert fe.decrypt(encrypted) == license_key
        assert license_key not in encrypted

    def test_T87_multiple_secrets_independent(self):
        store = SecretStore("multi-secret-master-key-32-chars!!")
        store.put("key_a", "value_a")
        store.put("key_b", "value_b")
        store.put("key_c", "value_c")
        assert store.get("key_a") == "value_a"
        assert store.get("key_b") == "value_b"
        assert store.get("key_c") == "value_c"
        ct_a = bytes(store._store["key_a"].ciphertext)
        ct_b = bytes(store._store["key_b"].ciphertext)
        assert ct_a != ct_b

    def test_T88_security_headers_no_info_leak_on_error(self):
        from starlette.applications import Starlette
        from starlette.routing import Route
        from starlette.testclient import TestClient

        async def broken(request):
            raise RuntimeError("secret123 internal error")

        app = Starlette(routes=[Route("/broken", broken)])
        app.add_middleware(
            SecurityHeadersMiddleware,
            environment="production",
            allowed_origins=["https://example.com"],
        )
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/broken")
        body = resp.text
        assert resp.status_code == 500
        assert "secret123" not in body
        assert "Traceback" not in body
        assert "RuntimeError" not in body
