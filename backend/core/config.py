"""
backend/core/config.py
Application configuration — all settings from environment variables.

Security:
- No default values for secrets
- JWT_SECRET_KEY minimum 32 chars enforced
- LICENSE_SALT required
- ENVIRONMENT restricts CORS wildcard
- Sentry auto-init if SENTRY_DSN provided
"""
from __future__ import annotations

import logging
import sys
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # App
    # ------------------------------------------------------------------
    APP_NAME: str = "Galaxy Vast AI Trading Platform"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = Field("production", pattern=r"^(development|staging|production)$")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------
    # Database (Supabase)
    # ------------------------------------------------------------------
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_KEY: str = Field(..., description="Supabase service role key")
    SUPABASE_JWT_SECRET: str = Field(..., min_length=32)

    # ------------------------------------------------------------------
    # JWT (internal)
    # ------------------------------------------------------------------
    JWT_SECRET_KEY: str = Field(..., min_length=32, description="Internal JWT signing secret")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(30, ge=1, le=90)

    # ------------------------------------------------------------------
    # Redis
    # ------------------------------------------------------------------
    REDIS_URL: str = Field("redis://redis:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(20, ge=5, le=100)

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"]
    )

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_IDS: str = Field("", description="Comma-separated admin user IDs")
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------
    BACKTEST_MAX_WORKERS: int = Field(4, ge=1, le=16)
    BACKTEST_JOB_TIMEOUT: int = Field(300, ge=30, le=3600)

    # ------------------------------------------------------------------
    # Licensing
    # ------------------------------------------------------------------
    LICENSE_SECRET: str = Field(..., description="License validation secret")
    LICENSE_SALT: str = Field(..., description="License salt (required)")

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------
    SENTRY_DSN: Optional[str] = None
    ENABLE_METRICS: bool = True
    API_BASE_URL: str = Field("http://api:8000")

    # ------------------------------------------------------------------
    # MQL5
    # ------------------------------------------------------------------
    MQL5_API_TOKEN: Optional[str] = None    # token for MQL5 EA → API auth

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, v) -> List[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            # Block wildcard CORS in production
            if "*" in self.ALLOWED_ORIGINS:
                log.critical(
                    "CRITICAL: CORS wildcard '*' not allowed in production. "
                    "Set ALLOWED_ORIGINS to your actual frontend domain."
                )
                sys.exit(1)

            # Block debug in production
            if self.DEBUG:
                log.warning("DEBUG=True in production — forcing False")
                object.__setattr__(self, "DEBUG", False)

        return self

    @model_validator(mode="after")
    def _init_sentry(self) -> "Settings":
        """Auto-init Sentry if DSN is provided."""
        if self.SENTRY_DSN:
            try:
                import sentry_sdk
                sentry_sdk.init(
                    dsn=self.SENTRY_DSN,
                    environment=self.ENVIRONMENT,
                    traces_sample_rate=0.1 if self.ENVIRONMENT == "production" else 1.0,
                    send_default_pii=False,   # never send PII
                )
                log.info("Sentry initialized for environment: %s", self.ENVIRONMENT)
            except ImportError:
                log.warning("SENTRY_DSN set but sentry-sdk not installed")
            except Exception as exc:
                log.warning("Sentry init failed: %s", exc)
        return self

    def get_admin_ids(self) -> List[int]:
        """Parse TELEGRAM_ADMIN_IDS into list of ints."""
        ids = []
        for part in self.TELEGRAM_ADMIN_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    try:
        settings = Settings()  # type: ignore[call-arg]
        log.info(
            "Settings loaded — environment: %s, debug: %s",
            settings.ENVIRONMENT,
            settings.DEBUG,
        )
        return settings
    except Exception as exc:
        log.critical("Failed to load settings: %s", exc)
        sys.exit(1)
