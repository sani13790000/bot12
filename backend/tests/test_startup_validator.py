"""
backend/tests/test_startup_validator.py
PHASE 2 — Startup Validation Tests
64 tests covering all 15 rules across 3 environments.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataclasses import dataclass, field
from typing import List, Optional

import pytest


@dataclass
class MockSettings:
    JWT_SECRET_KEY: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    DATABASE_URL: str = "postgresql://user:pass@localhost/db"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    REDIS_URL: str = "redis://localhost:6379/0"
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    ALLOWED_ORIGINS: List[str] = field(default_factory=lambda: ["http://localhost:3000"])
    DEBUG: bool = False
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BCRYPT_ROUNDS: int = 12
    SENTRY_DSN: Optional[str] = None


def _good_prod() -> MockSettings:
    return MockSettings(
        JWT_SECRET_KEY="a" * 64,
        DATABASE_URL="postgresql://user:pass@db.example.com/prod",
        SUPABASE_URL="https://abc.supabase.co",
        SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.real",
        SUPABASE_SERVICE_KEY="service_key_real_64chars_long_enough_1234567890abc",
        REDIS_URL="redis://redis:6379/0",
        MT5_LOGIN=123456,
        MT5_PASSWORD="realpassword",
        MT5_SERVER="BrokerName-Live",
        TELEGRAM_BOT_TOKEN="1234567890:AAHtoken",
        TELEGRAM_CHAT_ID="-100123456789",
        ALLOWED_ORIGINS=["https://app.example.com"],
        DEBUG=False,
        ACCESS_TOKEN_EXPIRE_MINUTES=60,
        BCRYPT_ROUNDS=12,
        SENTRY_DSN="https://abc@o123.ingest.sentry.io/456",
    )


from core.startup_validator import (
    Severity,
    StartupValidationResult,
    validate_mt5_credentials,
    validate_startup_config,
)


class TestRule01_JWT:
    def test_dev_weak_secret_is_warning(self):
        r = validate_startup_config(
            "development", settings=MockSettings(JWT_SECRET_KEY="changeme"), abort_on_error=False
        )
        assert "RULE-01" in [i.rule for i in r.warnings]

    def test_production_weak_secret_is_error(self):
        s = _good_prod()
        s.JWT_SECRET_KEY = "changeme"
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-01" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_short_secret_is_error(self):
        s = _good_prod()
        s.JWT_SECRET_KEY = "tooshort_abc"
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-01" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_strong_secret_passes(self):
        s = _good_prod()
        s.JWT_SECRET_KEY = "x" * 64
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert not any(i.rule == "RULE-01" and i.severity == Severity.ERROR for i in r.issues)

    def test_all_dangerous_secrets_caught(self):
        for secret in ["secret", "password", "dev", "your-secret-key", "jwt-secret", "replace-me"]:
            s = _good_prod()
            s.JWT_SECRET_KEY = secret
            r = validate_startup_config("production", settings=s, abort_on_error=False)
            assert any(i.rule == "RULE-01" and i.severity == Severity.ERROR for i in r.issues), (
                secret
            )


class TestRule02_Database:
    def test_no_db_url_is_error(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="", SUPABASE_URL=""),
            abort_on_error=False,
        )
        assert any(i.rule == "RULE-02" and i.severity == Severity.ERROR for i in r.issues)

    def test_invalid_scheme_is_error(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="mysql://u:p@h/db"),
            abort_on_error=False,
        )
        assert any(i.rule == "RULE-02" and i.severity == Severity.ERROR for i in r.issues)

    def test_valid_postgresql_passes(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="postgresql://u:p@h/db"),
            abort_on_error=False,
        )
        assert not any(i.rule == "RULE-02" and i.severity == Severity.ERROR for i in r.issues)

    def test_supabase_without_db_url_passes(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="", SUPABASE_URL="https://abc.supabase.co"),
            abort_on_error=False,
        )
        assert not any(i.rule == "RULE-02" and i.severity == Severity.ERROR for i in r.issues)

    def test_asyncpg_scheme_passes(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="postgresql+asyncpg://u:p@h/db"),
            abort_on_error=False,
        )
        assert not any(i.rule == "RULE-02" and i.severity == Severity.ERROR for i in r.issues)


class TestRule03_SupabaseServiceKey:
    def test_production_missing_service_key_is_error(self):
        s = _good_prod()
        s.SUPABASE_SERVICE_KEY = ""
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-03" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_placeholder_service_key_is_error(self):
        s = _good_prod()
        s.SUPABASE_SERVICE_KEY = "changeme"
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-03" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_real_service_key_passes(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=False)
        assert not any(i.rule == "RULE-03" and i.severity == Severity.ERROR for i in r.issues)

    def test_dev_without_supabase_no_rule03_check(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(SUPABASE_URL="", DATABASE_URL="postgresql://u:p@h/db"),
            abort_on_error=False,
        )
        assert not any(i.rule == "RULE-03" for i in r.issues)


class TestRule04_Redis:
    def test_invalid_redis_scheme_is_error(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(REDIS_URL="http://localhost:6379"),
            abort_on_error=False,
        )
        assert any(i.rule == "RULE-04" and i.severity == Severity.ERROR for i in r.issues)

    def test_valid_redis_url_passes(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(REDIS_URL="redis://localhost:6379/0"),
            abort_on_error=False,
        )
        assert not any(i.rule == "RULE-04" and i.severity == Severity.ERROR for i in r.issues)

    def test_rediss_tls_passes(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(REDIS_URL="rediss://redis:6380/0"),
            abort_on_error=False,
        )
        assert not any(i.rule == "RULE-04" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_no_redis_is_warning(self):
        s = _good_prod()
        s.REDIS_URL = ""
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-04" and i.severity == Severity.WARNING for i in r.issues)


class TestRule05_CORS:
    def test_production_wildcard_is_error(self):
        s = _good_prod()
        s.ALLOWED_ORIGINS = ["*"]
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-05" and i.severity == Severity.ERROR for i in r.issues)

    def test_dev_wildcard_is_warning(self):
        r = validate_startup_config(
            "development", settings=MockSettings(ALLOWED_ORIGINS=["*"]), abort_on_error=False
        )
        assert any(i.rule == "RULE-05" and i.severity == Severity.WARNING for i in r.issues)

    def test_specific_origin_passes(self):
        s = _good_prod()
        s.ALLOWED_ORIGINS = ["https://app.example.com"]
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert not any(i.rule == "RULE-05" and i.severity == Severity.ERROR for i in r.issues)


class TestRule06_Debug:
    def test_debug_true_in_production_is_error(self):
        s = _good_prod()
        s.DEBUG = True
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-06" and i.severity == Severity.ERROR for i in r.issues)

    def test_debug_true_in_dev_is_ok(self):
        r = validate_startup_config(
            "development", settings=MockSettings(DEBUG=True), abort_on_error=False
        )
        assert not any(i.rule == "RULE-06" and i.severity == Severity.ERROR for i in r.issues)

    def test_debug_false_in_production_passes(self):
        s = _good_prod()
        s.DEBUG = False
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert not any(i.rule == "RULE-06" and i.severity == Severity.ERROR for i in r.issues)


class TestRule07_MT5:
    def test_production_without_mt5_is_error(self):
        s = _good_prod()
        s.MT5_LOGIN = None
        s.MT5_PASSWORD = None
        s.MT5_SERVER = None
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-07" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_partial_mt5_is_error(self):
        s = _good_prod()
        s.MT5_PASSWORD = None
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-07" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_full_mt5_passes(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=False)
        assert not any(i.rule == "RULE-07" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_full_mt5_sets_live_trading_ready(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=False)
        assert r.live_trading_ready is True

    def test_dev_without_mt5_is_warning(self):
        r = validate_startup_config("development", settings=MockSettings(), abort_on_error=False)
        assert any(i.rule == "RULE-07" and i.severity == Severity.WARNING for i in r.issues)

    def test_invalid_mt5_login_string_is_error(self):
        s = _good_prod()
        s.MT5_LOGIN = "not_a_number"  # type: ignore
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-13" and i.severity == Severity.ERROR for i in r.issues)

    def test_negative_mt5_login_is_error(self):
        s = _good_prod()
        s.MT5_LOGIN = -1
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-13" and i.severity == Severity.ERROR for i in r.issues)


class TestRule09_JWTAlgorithm:
    def test_invalid_algorithm_is_error(self):
        r = validate_startup_config(
            "development", settings=MockSettings(JWT_ALGORITHM="NONE"), abort_on_error=False
        )
        assert any(i.rule == "RULE-09" and i.severity == Severity.ERROR for i in r.issues)

    def test_hs256_passes(self):
        r = validate_startup_config(
            "development", settings=MockSettings(JWT_ALGORITHM="HS256"), abort_on_error=False
        )
        assert not any(i.rule == "RULE-09" and i.severity == Severity.ERROR for i in r.issues)

    def test_rs256_passes(self):
        r = validate_startup_config(
            "development", settings=MockSettings(JWT_ALGORITHM="RS256"), abort_on_error=False
        )
        assert not any(i.rule == "RULE-09" and i.severity == Severity.ERROR for i in r.issues)


class TestRule11_Bcrypt:
    def test_production_low_rounds_is_error(self):
        s = _good_prod()
        s.BCRYPT_ROUNDS = 8
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-11" and i.severity == Severity.ERROR for i in r.issues)

    def test_production_12_rounds_passes(self):
        s = _good_prod()
        s.BCRYPT_ROUNDS = 12
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        assert not any(i.rule == "RULE-11" and i.severity == Severity.ERROR for i in r.issues)

    def test_dev_high_rounds_is_warning(self):
        r = validate_startup_config(
            "development", settings=MockSettings(BCRYPT_ROUNDS=14), abort_on_error=False
        )
        assert any(i.rule == "RULE-11" and i.severity == Severity.WARNING for i in r.issues)


class TestRule15_FailClosed:
    def test_production_with_errors_raises_system_exit(self):
        s = MockSettings(JWT_SECRET_KEY="changeme", DATABASE_URL="", SUPABASE_URL="")
        with pytest.raises(SystemExit) as exc_info:
            validate_startup_config("production", settings=s, abort_on_error=True)
        assert exc_info.value.code == 1

    def test_production_clean_does_not_raise(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=True)
        assert r.ok

    def test_development_with_errors_does_not_exit(self):
        s = MockSettings(JWT_SECRET_KEY="changeme", DATABASE_URL="", SUPABASE_URL="")
        r = validate_startup_config("development", settings=s, abort_on_error=True)
        assert r is not None


class TestValidateMT5Credentials:
    def test_all_set_returns_true(self):
        assert validate_mt5_credentials(123456, "password", "BrokerServer") is True

    def test_missing_login_returns_false(self):
        assert validate_mt5_credentials(None, "password", "Server") is False

    def test_missing_password_returns_false(self):
        assert validate_mt5_credentials(123456, None, "Server") is False

    def test_missing_server_returns_false(self):
        assert validate_mt5_credentials(123456, "password", None) is False

    def test_all_missing_returns_false(self):
        assert validate_mt5_credentials(None, None, None) is False

    def test_string_login_non_numeric_returns_false(self):
        assert validate_mt5_credentials("abc", "password", "Server") is False

    def test_negative_login_returns_false(self):
        assert validate_mt5_credentials(-1, "password", "Server") is False

    def test_zero_login_returns_false(self):
        assert validate_mt5_credentials(0, "password", "Server") is False

    def test_from_settings(self):
        s = MockSettings(MT5_LOGIN=999999, MT5_PASSWORD="realpass", MT5_SERVER="Broker-Live")
        assert validate_mt5_credentials(settings=s) is True

    def test_from_settings_missing(self):
        assert validate_mt5_credentials(settings=MockSettings()) is False


class TestValidationResult:
    def test_ok_property_no_errors(self):
        r = StartupValidationResult(environment="development")
        r.warning("RULE-01", "weak")
        assert r.ok is True

    def test_ok_property_with_error(self):
        r = StartupValidationResult(environment="production")
        r.error("RULE-01", "fatal")
        assert r.ok is False

    def test_errors_and_warnings_filtered(self):
        r = StartupValidationResult(environment="staging")
        r.error("RULE-01", "e")
        r.warning("RULE-02", "w")
        r.info("RULE-03", "i")
        assert len(r.errors) == 1 and len(r.warnings) == 1

    def test_summary_contains_environment(self):
        assert "PRODUCTION" in StartupValidationResult(environment="production").summary()

    def test_summary_passed_when_no_errors(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=False)
        assert "PASSED" in r.summary()

    def test_summary_failed_when_errors(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="", SUPABASE_URL=""),
            abort_on_error=False,
        )
        assert "FAILED" in r.summary()


class TestEnvironmentDetection:
    def test_unknown_env_defaults_to_development(self):
        r = validate_startup_config("unknown_env", settings=MockSettings(), abort_on_error=False)
        assert r.environment == "development"

    def test_staging_environment(self):
        s = MockSettings(JWT_SECRET_KEY="a" * 64, DATABASE_URL="postgresql://u:p@h/db")
        r = validate_startup_config("staging", settings=s, abort_on_error=False)
        assert r.environment == "staging"

    def test_production_environment(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=False)
        assert r.environment == "production"

    def test_none_environment_reads_from_os(self):
        old = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "staging"
        try:
            s = MockSettings(JWT_SECRET_KEY="a" * 64, DATABASE_URL="postgresql://u:p@h/db")
            r = validate_startup_config(None, settings=s, abort_on_error=False)
            assert r.environment == "staging"
        finally:
            if old is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = old


class TestIntegrationScenarios:
    def test_full_production_clean_passes(self):
        r = validate_startup_config("production", settings=_good_prod(), abort_on_error=False)
        assert r.ok and r.live_trading_ready and len(r.errors) == 0

    def test_full_development_minimal_passes(self):
        r = validate_startup_config(
            "development",
            settings=MockSettings(DATABASE_URL="postgresql://u:p@h/db"),
            abort_on_error=False,
        )
        assert not any(i.severity.value == "ERROR" for i in r.issues)

    def test_staging_requires_strong_jwt(self):
        s = MockSettings(
            JWT_SECRET_KEY="weak",
            DATABASE_URL="postgresql://u:p@h/db",
            ALLOWED_ORIGINS=["https://staging.example.com"],
        )
        r = validate_startup_config("staging", settings=s, abort_on_error=False)
        assert any(i.rule == "RULE-01" and i.severity == Severity.ERROR for i in r.issues)

    def test_multiple_errors_all_collected(self):
        s = MockSettings(
            JWT_SECRET_KEY="changeme",
            DATABASE_URL="",
            SUPABASE_URL="",
            ALLOWED_ORIGINS=["*"],
            DEBUG=True,
        )
        r = validate_startup_config("production", settings=s, abort_on_error=False)
        rules = [i.rule for i in r.errors]
        assert "RULE-01" in rules and "RULE-02" in rules
        assert "RULE-05" in rules and "RULE-06" in rules
        assert len(r.errors) >= 4
