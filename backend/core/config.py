"""backend/core/config.py v7 — Phase 3 Security Fix (S2)

A1-FIX: APP_VERSION, APP_ENV, TRUSTED_HOSTS, RATE_LIMIT_API_PER_MINUTE
S2-FIX: JWT_SECRET_KEY weak secret now raises ValueError in ALL environments
        UNLESS the env var TEST_MODE=true is set (for CI/unit-test pipelines).
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)

_DANGEROUS_SECRETS = {
    "changeme", "secret", "password", "test", "dev",
    "your-secret-key", "jwt-secret", "replace-me"
}
_ACCESS_TOKEN_MAX_MINUTES = 1440
_BCRYPT_ROUNDS_DEFAULT    = 12
_BCRYPT_ROUNDS_MIN        = 10
_BCRYPT_ROUNDS_MAX        = 14


def _detect_environment() -> str:
    env = (
        os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or os.environ.get("FASTAPI_ENV")
        or "development"
    ).lower()
    if env in ("prod", "production"):
        return "production"
    if env in ("staging", "stage"):
        return "staging"
    return "development"


def is_production() -> bool:
    return _detect_environment() == "production"


def _is_test_mode() -> bool:
    return os.environ.get("TEST_MODE", "").lower() in ("true", "1", "yes")


def get_bcrypt_rounds() -> int:
    try:
        rounds = int(os.environ.get("BCRYPT_ROUNDS", str(_BCRYPT_ROUNDS_DEFAULT)))
        return max(_BCRYPT_ROUNDS_MIN, min(_BCRYPT_ROUNDS_MAX, rounds))
    except (ValueError, TypeError):
        return _BCRYPT_ROUNDS_DEFAULT


class Settings(BaseSettings):
    APP_NAME: str = "Galaxy Vast AI"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = Field(default_factory=_detect_environment)

    @property
    def APP_ENV(self) -> str:
        return self.ENVIRONMENT

    JWT_SECRET_KEY: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    SECRET_KEY: str = ""
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=_ACCESS_TOKEN_MAX_MINUTES)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(
        default=_BCRYPT_ROUNDS_DEFAULT, ge=_BCRYPT_ROUNDS_MIN, le=_BCRYPT_ROUNDS_MAX
    )

    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    REDIS_URL: str = "redis://localhost:6379/0"

    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None

    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    MAX_RISK_PCT: float = Field(default=1.0, ge=0.1, le=10.0)
    MAX_DAILY_DRAWDOWN_PCT: float = Field(default=5.0, ge=0.5, le=20.0)
    INITIAL_ACCOUNT_BALANCE: float = Field(default=10_000.0, ge=100.0)
    MAX_OPEN_TRADES: int = Field(default=5, ge=1, le=50)

    DRIFT_THRESHOLD: float = Field(default=0.05, ge=0.01, le=0.5)
    ML_RETRAIN_INTERVAL_HOURS: int = Field(default=24, ge=1, le=168)

    RECONCILE_INTERVAL_SECONDS: int = Field(default=30, ge=5, le=300)
    SEMI_AUTO_PENDING_TTL_S: int = Field(default=300, ge=30, le=3600)
    BROKER_INIT_TIMEOUT_S: float = Field(default=30.0, ge=5.0, le=120.0)

    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    TRUSTED_HOSTS: List[str] = Field(default_factory=list)
    RATE_LIMIT_API_PER_MINUTE: int = Field(default=60, ge=1, le=10000)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if v.lower() in _DANGEROUS_SECRETS or len(v) < 32:
            if _is_test_mode():
                log.warning(
                    "[config] JWT_SECRET_KEY is weak — allowed because TEST_MODE=true"
                )
                return v
            raise ValueError(
                f"JWT_SECRET_KEY={v!r} is too weak or a known-dangerous default. "
                "Set a strong secret (>=32 chars) via JWT_SECRET_KEY env var. "
                "For tests/CI set TEST_MODE=true to bypass."
            )
        return v

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def _cap_token_expiry(cls, v: int) -> int:
        if v > _ACCESS_TOKEN_MAX_MINUTES:
            log.warning(
                "[config] ACCESS_TOKEN_EXPIRE_MINUTES capped to %d", _ACCESS_TOKEN_MAX_MINUTES
            )
            return _ACCESS_TOKEN_MAX_MINUTES
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _block_wildcard_in_prod(cls, v: List[str]) -> List[str]:
        if is_production() and "*" in v:
            raise ValueError("ALLOWED_ORIGINS='*' is not allowed in production")
        return v


def validate_settings(s: Settings) -> None:
    if not s.DATABASE_URL and not s.SUPABASE_URL:
        log.warning("[config] Neither DATABASE_URL nor SUPABASE_URL is set")
    if s.DATABASE_URL and not s.DATABASE_URL.startswith(("postgresql", "postgres", "sqlite")):
        log.warning("[config] DATABASE_URL has unexpected scheme: %s", s.DATABASE_URL[:30])
    if not s.SECRET_KEY:
        log.warning("[config] SECRET_KEY not set — refresh token signing will use JWT_SECRET_KEY")


def patch_config_at_startup() -> None:
    s = get_settings()
    validate_settings(s)
    log.debug("[config] environment=%s, production=%s", _detect_environment(), is_production())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
