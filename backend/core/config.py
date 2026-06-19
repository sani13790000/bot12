"""backend/core/config.py — production-hardened v3.

FIX-7  sys.exit() in model_validator kills pytest. Now raises RuntimeError.
        get_settings() catches it and calls sys.exit(1) at startup only.
FIX-8  Sentry init moved out of model_validator to explicit _init_sentry().
FIX-9  TRUSTED_PROXY_CIDRS setting added for client_ip.py.
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

    APP_NAME: str = "Galaxy Vast AI Trading Platform"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = Field("production", pattern=r"^(development|staging|production)$")
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    SUPABASE_URL: str = Field(..., description="Supabase project URL")
    SUPABASE_KEY: str = Field(..., description="Supabase service role key")
    SUPABASE_JWT_SECRET: str = Field(..., min_length=32)

    JWT_SECRET_KEY: str = Field(..., min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(30, ge=1, le=90)

    REDIS_URL: str = Field("redis://redis:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(20, ge=5, le=100)

    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"]
    )

    # FIX-9: TRUSTED_PROXY_CIDRS for client_ip.py
    TRUSTED_PROXY_CIDRS: str = Field(
        default="",
        description=(
            "Comma-separated CIDRs of trusted reverse proxies. "
            "Empty = use default private ranges."
        ),
    )

    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_ADMIN_IDS: str = Field("")
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

    BACKTEST_MAX_WORKERS: int = Field(4, ge=1, le=16)
    BACKTEST_JOB_TIMEOUT: int = Field(300, ge=30, le=3600)

    LICENSE_SECRET: str = Field(...)
    LICENSE_SALT: str = Field(...)

    SENTRY_DSN: Optional[str] = None
    ENABLE_METRICS: bool = True
    API_BASE_URL: str = Field("http://api:8000")
    MQL5_API_TOKEN: Optional[str] = None

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, v) -> List[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _validate_production_settings(self) -> "Settings":
        """
        FIX-7: raises RuntimeError instead of sys.exit().
        sys.exit() inside a Pydantic validator kills pytest collection.
        get_settings() catches RuntimeError and exits at startup.
        """
        if self.ENVIRONMENT == "production":
            if "*" in self.ALLOWED_ORIGINS:
                raise RuntimeError(
                    "CORS wildcard '*' is not allowed in production. "
                    "Set ALLOWED_ORIGINS to your actual frontend domain(s)."
                )
            if self.DEBUG:
                log.warning("DEBUG=True in production — forcing False")
                object.__setattr__(self, "DEBUG", False)
        return self

    def _init_sentry(self) -> None:
        """
        FIX-8: Sentry init moved out of model_validator.
        Called explicitly from get_settings() after construction.
        """
        if not self.SENTRY_DSN:
            return
        try:
            import sentry_sdk
            sentry_sdk.init(
                dsn=self.SENTRY_DSN,
                environment=self.ENVIRONMENT,
                traces_sample_rate=0.1 if self.ENVIRONMENT == "production" else 1.0,
                send_default_pii=False,
            )
            log.info("Sentry initialized for environment: %s", self.ENVIRONMENT)
        except ImportError:
            log.warning("SENTRY_DSN set but sentry-sdk not installed")
        except Exception as exc:
            log.warning("Sentry init failed: %s", exc)

    def get_admin_ids(self) -> List[int]:
        ids: List[int] = []
        for part in self.TELEGRAM_ADMIN_IDS.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
        return ids


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    FIX-7: sys.exit(1) here is correct — startup path only.
    RuntimeError from validator is caught here, not in validator itself.
    """
    try:
        s = Settings()  # type: ignore[call-arg]
        s._init_sentry()  # FIX-8: explicit call after construction
        log.info(
            "Settings loaded — environment: %s, debug: %s",
            s.ENVIRONMENT,
            s.DEBUG,
        )
        return s
    except RuntimeError as exc:
        log.critical("Configuration error: %s", exc)
        sys.exit(1)
    except Exception as exc:
        log.critical("Failed to load settings: %s", exc)
        sys.exit(1)


settings = get_settings()
