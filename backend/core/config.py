"""backend/core/config.py v5 - Phase T + Phase1 Merge

T-13: INITIAL_ACCOUNT_BALANCE added
T-14: API_PREFIX added
T-15: RECONCILE_INTERVAL_SECONDS added
T-16: MT5_LOGIN / MT5_PASSWORD / MT5_SERVER added
T-17: SEMI_AUTO_PENDING_TTL_S added
T-18: DRIFT_THRESHOLD added
PHASE1-MERGE T-25..T-30 from config_patch.py:
  T-25: JWT_SECRET_KEY validation against dangerous defaults
  T-26: DATABASE_URL format validation
  T-27: ACCESS_TOKEN_EXPIRE_MINUTES upper cap (1440)
  T-28: CORS wildcard blocked in production
  T-29: Environment detection (_detect_environment)
  T-30: BCRYPT_ROUNDS configurable
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)

# ── Patch constants (T-25..T-30) ──────────────────────────────────────────────
_DANGEROUS_SECRETS = {
    "changeme", "secret", "password", "test", "dev",
    "your-secret-key", "jwt-secret", "replace-me"
}
_ACCESS_TOKEN_MAX_MINUTES = 1440   # 24 h cap
_BCRYPT_ROUNDS_DEFAULT    = 12
_BCRYPT_ROUNDS_MIN        = 10
_BCRYPT_ROUNDS_MAX        = 14


def _detect_environment() -> str:
    """T-29: Detect environment from common env vars."""
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


def get_bcrypt_rounds() -> int:
    """T-30: Returns configurable bcrypt rounds (10-14)."""
    try:
        rounds = int(os.environ.get("BCRYPT_ROUNDS", str(_BCRYPT_ROUNDS_DEFAULT)))
        return max(_BCRYPT_ROUNDS_MIN, min(_BCRYPT_ROUNDS_MAX, rounds))
    except (ValueError, TypeError):
        return _BCRYPT_ROUNDS_DEFAULT


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Core
    APP_NAME: str = "Galaxy Vast AI"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = Field(default_factory=_detect_environment)

    # Security
    JWT_SECRET_KEY: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=_ACCESS_TOKEN_MAX_MINUTES)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(default=_BCRYPT_ROUNDS_DEFAULT, ge=_BCRYPT_ROUNDS_MIN, le=_BCRYPT_ROUNDS_MAX)

    # Database
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # MT5
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None

    # Risk
    MAX_RISK_PCT: float = Field(default=1.0, ge=0.1, le=10.0)
    MAX_DAILY_DRAWDOWN_PCT: float = Field(default=5.0, ge=0.5, le=20.0)
    INITIAL_ACCOUNT_BALANCE: float = Field(default=10_000.0, ge=100.0)
    MAX_OPEN_TRADES: int = Field(default=5, ge=1, le=50)

    # ML
    DRIFT_THRESHOLD: float = Field(default=0.05, ge=0.01, le=0.5)
    ML_RETRAIN_INTERVAL_HOURS: int = Field(default=24, ge=1, le=168)

    # Execution
    RECONCILE_INTERVAL_SECONDS: int = Field(default=30, ge=5, le=300)
    SEMI_AUTO_PENDING_TTL_S: int = Field(default=300, ge=30, le=3600)
    BROKER_INIT_TIMEOUT_S: float = Field(default=30.0, ge=5.0, le=120.0)

    # CORS
    ALLOWED_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        if v.lower() in _DANGEROUS_SECRETS:
            if is_production():
                raise ValueError(
                    f"JWT_SECRET_KEY={v!r} is a known-dangerous default. "
                    "Set a strong secret in production."
                )
            log.warning("[config] JWT_SECRET_KEY is a known-dangerous default (T-25)")
        return v

    @field_validator("ACCESS_TOKEN_EXPIRE_MINUTES")
    @classmethod
    def _cap_token_expiry(cls, v: int) -> int:
        if v > _ACCESS_TOKEN_MAX_MINUTES:
            log.warning("[config] ACCESS_TOKEN_EXPIRE_MINUTES capped to %d (T-27)", _ACCESS_TOKEN_MAX_MINUTES)
            return _ACCESS_TOKEN_MAX_MINUTES
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _block_wildcard_in_prod(cls, v: List[str]) -> List[str]:
        if is_production() and "*" in v:
            raise ValueError("ALLOWED_ORIGINS='*' is not allowed in production (T-28)")
        return v


def validate_settings(s: Settings) -> None:
    """T-26: Validate DATABASE_URL and other critical fields at startup."""
    if not s.DATABASE_URL and not s.SUPABASE_URL:
        log.warning("[config] Neither DATABASE_URL nor SUPABASE_URL is set (T-26)")
    if s.DATABASE_URL and not s.DATABASE_URL.startswith(("postgresql", "postgres", "sqlite")):
        log.warning("[config] DATABASE_URL has unexpected scheme (T-26): %s", s.DATABASE_URL[:30])


def patch_config_at_startup() -> None:
    """Call once at startup to validate and log config state."""
    s = get_settings()
    validate_settings(s)
    log.debug("[config] environment=%s, production=%s", _detect_environment(), is_production())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
