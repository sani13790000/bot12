"""Application configuration — all settings from environment variables.

All REQUIRED fields use Field(...) with no default.
Missing required fields cause sys.exit(1) at startup.
"""
from __future__ import annotations

import logging
import sys
from typing import List, Optional

try:
    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings
except ImportError as exc:  # noqa: BLE001
    print(f"FATAL: pydantic/pydantic-settings not installed: {exc}")
    sys.exit(1)

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Platform-wide settings loaded from environment / .env file."""

    # ------------------------------------------------------------------ #
    # Supabase
    # ------------------------------------------------------------------ #
    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_ANON_KEY: str = Field(..., description="Supabase anon/public key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., description="Supabase service role key")

    # ------------------------------------------------------------------ #
    # JWT
    # ------------------------------------------------------------------ #
    JWT_SECRET_KEY: str = Field(..., min_length=32, description="JWT signing secret (min 32 chars)")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, ge=1, le=90)

    # ------------------------------------------------------------------ #
    # Redis
    # ------------------------------------------------------------------ #
    REDIS_URL: str = Field("redis://redis:6379/0", description="Redis connection URL")

    # ------------------------------------------------------------------ #
    # App
    # ------------------------------------------------------------------ #
    ENVIRONMENT: str = Field("development", description="development | staging | production")
    LOG_LEVEL: str = Field("INFO", description="Python logging level")
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"],
        description="CORS allowed origins",
    )

    # ------------------------------------------------------------------ #
    # License
    # ------------------------------------------------------------------ #
    LICENSE_KEY: str = Field(..., description="Platform license key")
    LICENSE_SALT: str = Field(..., description="License hashing salt (no default — must be set)")

    # ------------------------------------------------------------------ #
    # Telegram
    # ------------------------------------------------------------------ #
    TELEGRAM_BOT_TOKEN: str = Field(..., description="Telegram bot token")
    TELEGRAM_CHAT_ID: str = Field(..., description="Telegram chat/channel ID")

    # ------------------------------------------------------------------ #
    # Backtest tuning
    # ------------------------------------------------------------------ #
    BACKTEST_MAX_WORKERS: int = Field(4, ge=1, le=16, description="ProcessPoolExecutor workers")

    # ------------------------------------------------------------------ #
    # Optional integrations — NOT required at startup
    # ------------------------------------------------------------------ #
    # Sentry: set SENTRY_DSN in .env to enable error tracking.
    # If not set, Sentry is silently disabled — no startup error.
    SENTRY_DSN: Optional[str] = Field(None, description="Sentry DSN (optional — omit to disable)")

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}, got '{v}'")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def no_wildcard_in_production(cls, v: List[str], info) -> List[str]:  # type: ignore[override]
        # We can't easily access other fields here in pydantic v2 validators,
        # so we guard at app startup in main.py instead.
        if "*" in v:
            logger.warning("ALLOWED_ORIGINS contains wildcard '*' — ensure this is intentional.")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


def _load_settings() -> Settings:
    """Load and validate settings; exit with a clear message on failure."""
    try:
        s = Settings()  # type: ignore[call-arg]

        # Extra runtime guard: wildcard CORS in production is a security risk
        if s.ENVIRONMENT == "production" and "*" in s.ALLOWED_ORIGINS:
            print(
                "FATAL: ALLOWED_ORIGINS contains '*' in production environment.\n"
                "Set ALLOWED_ORIGINS to your actual frontend origin(s) in .env."
            )
            sys.exit(1)

        # Initialise Sentry if DSN is provided
        if s.SENTRY_DSN:
            try:
                import sentry_sdk  # type: ignore[import]

                sentry_sdk.init(
                    dsn=s.SENTRY_DSN,
                    environment=s.ENVIRONMENT,
                    traces_sample_rate=0.1,
                )
                logger.info("Sentry initialised (environment=%s).", s.ENVIRONMENT)
            except ImportError:
                logger.warning(
                    "SENTRY_DSN is set but sentry-sdk is not installed. "
                    "Add sentry-sdk to requirements.txt to enable error tracking."
                )

        return s

    except Exception as exc:  # noqa: BLE001
        print(
            f"\n{'='*60}\n"
            f"FATAL: Configuration error\n"
            f"{exc}\n"
            f"Run: python3 startup_check.py to validate your .env file\n"
            f"{'='*60}\n"
        )
        sys.exit(1)


settings = _load_settings()
