"""
backend/core/config.py v9 - FIXED
Fixes:
  BUG-5 FIX: REDIS_PASSWORD added to Settings + REDIS_URL_WITH_AUTH property
  AI-4 FIX: MT5_GATEWAY_URL added to Settings
  AI-6 FIX: TELEGRAM_ADMIN_IDS, ADMIN_IP_ALLOWLIST added
  AI-7 FIX: SECRET_KEY empty-string warning improved
  AI-8 FIX: RECONCILE_INTERVAL_SECONDS documented in validate_settings
Previous fixes retained:
  A1-FIX: APP_VERSION, APP_ENV, TRUSTED_HOSTS, RATE_LIMIT_API_PER_MINUTE
  S2-FIX: JWT_SECRET_KEY weak raises ValueError (unless TEST_MODE=true)
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import List, Optional
from urllib.parse import urlparse, urlunparse

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
    APP_NAME:    str = "Galaxy Vast AI"
    APP_VERSION: str = "3.0.0"
    DEBUG:       bool = False
    API_PREFIX:  str = "/api/v1"
    ENVIRONMENT: str = Field(default_factory=_detect_environment)

    @property
    def APP_ENV(self) -> str:
        return self.ENVIRONMENT

    # Auth
    JWT_SECRET_KEY: str = "changeme"
    JWT_ALGORITHM:  str = "HS256"
    SECRET_KEY:     str = ""
    ALGORITHM:      str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=_ACCESS_TOKEN_MAX_MINUTES)
    REFRESH_TOKEN_EXPIRE_DAYS:   int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(
        default=_BCRYPT_ROUNDS_DEFAULT, ge=_BCRYPT_ROUNDS_MIN, le=_BCRYPT_ROUNDS_MAX
    )

    # Database
    DATABASE_URL:        str = ""
    SUPABASE_URL:        str = ""
    SUPABASE_KEY:        str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Cache
    # BUG-5 FIX: REDIS_PASSWORD was in docker-compose but never parsed here.
    # docker-compose starts Redis with: --requirepass ${REDIS_PASSWORD}
    # Without this, every Redis command fails with NOAUTH error.
    REDIS_URL:      str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""

    @property
    def REDIS_URL_WITH_AUTH(self) -> str:
        """Returns REDIS_URL with password injected if REDIS_PASSWORD is set.
        Use this in redis_client.py instead of bare REDIS_URL.
        """
        if not self.REDIS_PASSWORD:
            return self.REDIS_URL
        parsed = urlparse(self.REDIS_URL)
        if parsed.password:
            return self.REDIS_URL  # already has credentials
        netloc = f":{self.REDIS_PASSWORD}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        return urlunparse(parsed._replace(netloc=netloc))

    # MT5
    MT5_LOGIN:           Optional[int] = None
    MT5_PASSWORD:        Optional[str] = None
    MT5_SERVER:          Optional[str] = None
    MT5_GATEWAY_URL:     str   = "http://localhost:8080"
    MT5_DEMO_MODE:       bool  = True
    MT5_GATEWAY_TIMEOUT: float = Field(default=10.0, ge=1.0, le=60.0)
    MT5_MAX_RETRIES:     int   = Field(default=3, ge=1, le=10)

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID:   Optional[str] = None
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)

    # Security
    ADMIN_IP_ALLOWLIST: List[str] = Field(default_factory=list)

    # Risk
    MAX_RISK_PCT:            float = Field(default=1.0,      ge=0.1, le=10.0)
    MAX_DAILY_DRAWDOWN_PCT:  float = Field(default=5.0,      ge=0.5, le=20.0)
    INITIAL_ACCOUNT_BALANCE: float = Field(default=10_000.0, ge=100.0)
    MAX_OPEN_TRADES:         int   = Field(default=5,        ge=1,   le=50)

    # ML
    DRIFT_THRESHOLD:           float = Field(default=0.05, ge=0.01, le=0.5)
    ML_RETRAIN_INTERVAL_HOURS: int   = Field(default=24,   ge=1,    le=168)

    # Scheduler
    RECONCILE_INTERVAL_SECONDS: int = Field(default=30, ge=5, le=300)
    SEMI_AUTO_PENDING_TTL_S:    int = Field(default=300, ge=30)
    BROKER_INIT_TIMEOUT_S:     float = Field(default=30.0, ge=5.0)

    # API
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])
    TRUSTED_HOSTS:   List[str] = Field(default_factory=list)
    RATE_LIMIT_API_PER_MINUTE: int = Field(default=60, ge=1, le=10000)

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def validate_settings(s: Settings) -> None:
    env = s.ENVIRONMENT
    test = _is_test_mode()

    # JWT Secret
    if s.JWT_SECRET_KEY.lower() in _DANGEROUS_SECRETS or len(s.JWT_SECRET_KEY) < 32:
        if env == "production" and not test:
            raise ValueError(
                f"JWT_SECRET_KEY is weak ({s.JWT_SECRET_KEY!r}). "
                "Set a strong random secret (>= 32 chars) in production."
            )
        else:
            log.warning("[Config] JWT_SECRET_KEY is weak -- OK for dev/test, CHANGE for production")

    # Refresh token secret
    if not s.SECRET_KEY:
        log.warning(
            "[Config] SECRET_KEY is empty -- refresh tokens will be unsigned! "
            "Set SECRET_KEY in .env"
        )

    # Redis auth
    if not s.REDIS_PASSWORD:
        log.warning(
            "[Config] REDIS_PASSWORD not set. If Redis uses --requirepass, "
            "all cache operations will fail with NOAUTH. Set REDIS_PASSWORD in .env"
        )

    # Scheduler config
    if s.RECONCILE_INTERVAL_SECONDS:
        log.debug(
            "[Config] RECONCILE_INTERVAL_SECONDS=%d -- "
            "wire a background scheduler in lifespan to use this",
            s.RECONCILE_INTERVAL_SECONDS,
        )

    # Supabase
    if not s.SUPABASE_URL or not s.SUPABASE_KEY:
        log.warning("[Config] SUPABASE_URL or SUPABASE_KEY not set -- DB will fail")


# Module-level singleton for backward compat
settings = get_settings()
