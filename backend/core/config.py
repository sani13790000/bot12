"""backend/core/config.py v8 - Phase C Extended

Phase C additions over v7:
  - SESSION_COOKIE_SECURE, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_HTTPONLY
  - CSP_ENABLED, CSP_REPORT_ONLY, CSP_REPORT_URI
  - LICENSE_REPLAY_WINDOW_SECONDS for LicenseEngine
  - BACKTEST_MAX_WORKERS, BACKTEST_JOB_TIMEOUT
  - ENABLE_METRICS, API_BASE_URL
  - ADMIN_IP_ALLOWLIST field_validator (parse comma-separated string)
  - TELEGRAM_WEBHOOK_SECRET
  - production warnings for missing LICENSE_SECRET, FIELD_ENCRYPTION_KEY,
    SECRETS_MASTER_KEY, and wildcard ALLOWED_ORIGINS
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


def get_bcrypt_rounds() -> int:
    try:
        rounds = int(os.environ.get("BCRYPT_ROUNDS", str(_BCRYPT_ROUNDS_DEFAULT)))
        return max(_BCRYPT_ROUNDS_MIN, min(_BCRYPT_ROUNDS_MAX, rounds))
    except (ValueError, TypeError):
        return _BCRYPT_ROUNDS_DEFAULT


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Core
    APP_NAME: str = "Galaxy Vast AI"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = Field(default_factory=_detect_environment)

    @property
    def APP_ENV(self) -> str:
        return self.ENVIRONMENT

    # Security / JWT
    JWT_SECRET_KEY: str = "changeme"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=_ACCESS_TOKEN_MAX_MINUTES)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(default=_BCRYPT_ROUNDS_DEFAULT, ge=_BCRYPT_ROUNDS_MIN, le=_BCRYPT_ROUNDS_MAX)

    # Cookie Security (Phase C)
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "strict"
    SESSION_COOKIE_HTTPONLY: bool = True

    # Content Security Policy (Phase C)
    CSP_ENABLED: bool = True
    CSP_REPORT_ONLY: bool = False
    CSP_REPORT_URI: str = "/api/v1/csp-report"

    # CORS & Hosts
    ALLOWED_ORIGINS: List[str] = ["*"]
    TRUSTED_HOSTS: List[str] = []

    # Rate limiting
    RATE_LIMIT_API_PER_MINUTE: int = Field(default=60, ge=1, le=10000)

    # Database
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: str = ""
    REDIS_MAX_CONNECTIONS: int = Field(default=10, ge=1, le=100)

    @property
    def REDIS_URL_WITH_AUTH(self) -> str:
        if not self.REDIS_PASSWORD:
            return self.REDIS_URL
        url = self.REDIS_URL
        if "://" in url:
            scheme, rest = url.split("://", 1)
            if "@" not in rest:
                return f"{scheme}://:{self.REDIS_PASSWORD}@{rest}"
        return url

    # MT5
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None
    MT5_GATEWAY_URL: str = "http://localhost:8080"
    MT5_DEMO_MODE: bool = True
    GATEWAY_API_KEY: str = ""

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    TELEGRAM_ADMIN_IDS: List[int] = []
    TELEGRAM_WEBHOOK_SECRET: str = ""

    # Admin
    ADMIN_IP_ALLOWLIST: List[str] = []

    # Encryption & Secrets
    SECRETS_MASTER_KEY: str = ""
    FIELD_ENCRYPTION_KEY: str = ""

    # License
    LICENSE_SECRET: str = ""
    LICENSE_SALT: str = ""
    MQL5_API_TOKEN: str = ""
    LICENSE_REPLAY_WINDOW_SECONDS: int = Field(default=3600, ge=60, le=86400)

    # Payments
    STRIPE_WEBHOOK_SECRET: str = ""
    ZARINPAL_WEBHOOK_SECRET: str = ""

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_REDACTION_ENABLED: bool = True

    # Risk & Trading
    MAX_DAILY_LOSS_PCT: float = Field(default=5.0, ge=0.1, le=50.0)
    MAX_POSITION_SIZE_PCT: float = Field(default=2.0, ge=0.01, le=10.0)
    MAX_OPEN_TRADES: int = Field(default=5, ge=1, le=50)
    DEFAULT_RISK_PER_TRADE_PCT: float = Field(default=1.0, ge=0.01, le=5.0)
    RECONCILE_INTERVAL_SECONDS: int = Field(default=30, ge=5, le=300)
    SEMI_AUTO_PENDING_TTL_S: int = Field(default=300, ge=30, le=3600)
    BROKER_INIT_TIMEOUT_S: float = Field(default=30.0, ge=5.0, le=120.0)

    # Backtest (Phase C)
    BACKTEST_MAX_WORKERS: int = Field(default=4, ge=1, le=16)
    BACKTEST_JOB_TIMEOUT: int = Field(default=300, ge=30, le=3600)

    # Observability (Phase C)
    ENABLE_METRICS: bool = True
    API_BASE_URL: str = ""

    # Feature flags
    KILL_SWITCH_ENABLED: bool = True
    SELF_LEARNING_ENABLED: bool = True
    TEST_MODE: bool = False

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _validate_jwt_secret(cls, v: str) -> str:
        env = _detect_environment()
        if env == "production" and v.lower() in _DANGEROUS_SECRETS:
            raise ValueError(
                "JWT_SECRET_KEY is a weak/default value in production. "
                "Set a strong random secret (min 32 chars)."
            )
        if v.lower() in _DANGEROUS_SECRETS:
            log.warning("[config] JWT_SECRET_KEY is weak. Set a strong secret for production.")
        return v

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("TRUSTED_HOSTS", mode="before")
    @classmethod
    def _parse_hosts(cls, v: object) -> object:
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v

    @field_validator("TELEGRAM_ADMIN_IDS", mode="before")
    @classmethod
    def _parse_admin_ids(cls, v: object) -> object:
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("ADMIN_IP_ALLOWLIST", mode="before")
    @classmethod
    def _parse_ip_allowlist(cls, v: object) -> object:
        if isinstance(v, str):
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        return v

    model_config = {"extra": "ignore", "env_file": ".env", "env_file_encoding": "utf-8"}


def validate_settings(s: Settings) -> None:
    if not s.DATABASE_URL and not s.SUPABASE_URL:
        log.warning("[config] Neither DATABASE_URL nor SUPABASE_URL is set")
    if s.DATABASE_URL and not s.DATABASE_URL.startswith(("postgresql", "postgres", "sqlite")):
        log.warning("[config] DATABASE_URL unexpected scheme: %s", s.DATABASE_URL[:30])
    if is_production():
        if not s.LICENSE_SECRET:
            log.error("[config] LICENSE_SECRET not set in production - license system disabled")
        if not s.FIELD_ENCRYPTION_KEY:
            log.error("[config] FIELD_ENCRYPTION_KEY not set - field encryption disabled")
        if not s.SECRETS_MASTER_KEY:
            log.error("[config] SECRETS_MASTER_KEY not set")
        if s.ALLOWED_ORIGINS == ["*"]:
            log.warning("[config] ALLOWED_ORIGINS is wildcard in production - restrict to your domains")


def patch_config_at_startup() -> None:
    s = get_settings()
    validate_settings(s)
    log.debug("[config] environment=%s, production=%s", _detect_environment(), is_production())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
