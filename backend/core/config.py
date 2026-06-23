"""backend/core/config.py v4 - Phase T

T-13: INITIAL_ACCOUNT_BALANCE added (was missing -> equity init with 0)
T-14: API_PREFIX added (was missing -> telegram handlers AttributeError)
T-15: RECONCILE_INTERVAL_SECONDS added with ge=5, le=300
T-16: MT5_LOGIN / MT5_PASSWORD / MT5_SERVER added to Settings
T-17: SEMI_AUTO_PENDING_TTL_S added
T-18: DRIFT_THRESHOLD added
"""
from __future__ import annotations
import logging, os, sys
from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    APP_NAME:    str = "Galaxy Vast AI Trading Platform"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = Field("production", pattern=r"^(development|staging|production)$")
    DEBUG:       bool = False
    LOG_LEVEL:   str  = "INFO"

    SUPABASE_URL:        str = Field(..., description="Supabase project URL")
    SUPABASE_KEY:        str = Field(..., description="Supabase service role key")
    SUPABASE_JWT_SECRET: str = Field(..., min_length=32)
    JWT_SECRET_KEY:      str = Field(..., min_length=32)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30,  ge=5,  le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS:   int = Field(30,  ge=1,  le=90)

    REDIS_URL:             str = Field("redis://redis:6379/0")
    REDIS_MAX_CONNECTIONS: int = Field(20, ge=5, le=100)

    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"]
    )
    TRUSTED_PROXY_CIDRS: str = Field(default="")

    TELEGRAM_BOT_TOKEN:      Optional[str] = None
    TELEGRAM_ADMIN_IDS:      str           = Field("")
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

    BACKTEST_MAX_WORKERS: int = Field(4,   ge=1, le=16)
    BACKTEST_JOB_TIMEOUT: int = Field(300, ge=30, le=3600)
    LICENSE_SECRET: str = Field(...)
    LICENSE_SALT:   str = Field(...)
    SENTRY_DSN:     Optional[str] = None
    ENABLE_METRICS: bool = True
    API_BASE_URL:   str  = Field("http://api:8000")
    MQL5_API_TOKEN: Optional[str] = None

    # T-14: used by telegram handlers
    API_PREFIX: str = Field(default="/api/v1")

    # T-13: EquityProtection cold-start balance
    INITIAL_ACCOUNT_BALANCE: float = Field(default=10_000.0, ge=0.0)

    # T-15: position reconciliation interval
    RECONCILE_INTERVAL_SECONDS: int = Field(default=10, ge=5, le=300)

    # T-16: MT5 credentials
    MT5_LOGIN:    Optional[int] = Field(default=None)
    MT5_PASSWORD: Optional[str] = Field(default=None)
    MT5_SERVER:   Optional[str] = Field(default=None)
    MT5_PATH:     Optional[str] = Field(default=None)
    MT5_REVALIDATE_TIMEOUT:   float = Field(default=5.0,  ge=1.0, le=30.0)
    MT5_REVALIDATE_RETRIES:   int   = Field(default=3,    ge=1,   le=10)
    MT5_SLIPPAGE_BASE:        int   = Field(default=10,   ge=1,   le=100)
    MT5_SLIPPAGE_MAX:         int   = Field(default=50,   ge=1,   le=200)
    MT5_SLIPPAGE_ATR_MULT:    float = Field(default=2.0,  ge=0.0, le=10.0)
    MT5_SLIPPAGE_SPREAD_MULT: float = Field(default=1.5,  ge=0.0, le=10.0)

    # T-17: semi-auto signal expiry
    SEMI_AUTO_PENDING_TTL_S: int = Field(default=300, ge=30, le=3600)

    # T-18: ML drift threshold
    DRIFT_THRESHOLD: float = Field(default=0.08, ge=0.0, le=1.0)

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _parse_origins(cls, v) -> List[str]:
        if isinstance(v, str): return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if "*" in self.ALLOWED_ORIGINS:
                raise RuntimeError("CORS wildcard not allowed in production")
            if self.DEBUG:
                object.__setattr__(self, "DEBUG", False)
        return self

    def _init_sentry(self) -> None:
        if not self.SENTRY_DSN: return
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=self.SENTRY_DSN, environment=self.ENVIRONMENT,
                            traces_sample_rate=0.1, send_default_pii=False)
        except ImportError:
            log.warning("sentry-sdk not installed")
        except Exception as exc:
            log.error("Sentry init failed: %s", exc)

    def get_admin_ids(self) -> List[int]:
        if not self.TELEGRAM_ADMIN_IDS: return []
        return [int(p.strip()) for p in self.TELEGRAM_ADMIN_IDS.split(",") if p.strip().isdigit()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        s = Settings()  # type: ignore[call-arg]
        s._init_sentry()
        return s
    except RuntimeError as exc:
        log.critical("Settings validation failed: %s", exc)
        sys.exit(1)
    except Exception as exc:
        log.critical("Could not load settings: %s", exc)
        sys.exit(1)


if not os.environ.get("PYTEST_CURRENT_TEST"):
    try:
        settings = get_settings()
    except SystemExit:
        raise
else:
    settings = None  # type: ignore[assignment]
