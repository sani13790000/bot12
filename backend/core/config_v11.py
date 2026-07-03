"""
backend/core/config_v11.py
Galaxy Vast AI - Config Phase 11 Patches

P11-CFG-1: SECRETS_MASTER_KEY required in production
P11-CFG-2: ALLOWED_ORIGINS strict validation
P11-CFG-3: LOG_REDACTER enabled by default
P11-CFG-4: FIELD_ENCRYPTION_KEY hex validation
"""
from __future__ import annotations
import os
import re
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

_ORIGIN_RE = re.compile(r'^https?://[a-zA-Z0-9.-]+(:\d+)?$')


class PhaseConfig(BaseSettings):
    # Security
    JWT_SECRET_KEY: str = Field(default="changeme")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=14)

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
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

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

    # Phase 11 additions
    SECRETS_MASTER_KEY: str = Field(default="")
    CSP_ENABLED: bool = True
    CSP_REPORT_ONLY: bool = False
    CSP_REPORT_URI: str = "/api/v1/csp-report"
    LOG_REDACTER_ENABLED: bool = True
    FIELD_ENCRYPTION_KEY: str = ""
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "strict"
    SESSION_COOKIE_HTTPONLY: bool = True
    STRIPE_WEBHOOK_SECRET: str = ""
    ZARINPAL_WEBHOOK_SECRET: str = ""
    LICENSE_SECRET: str = ""
    LICENSE_SALT: str = ""

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _validate_origins(cls, v: List[str]) -> List[str]:
        if isinstance(v, str):
            v = [x.strip() for x in v.split(",")]
        for origin in v:
            if not _ORIGIN_RE.match(origin):
                raise ValueError(f"P11-CFG-2 Invalid origin format: {origin!r}. Must be scheme://host[:port]")
        return v

    @field_validator("FIELD_ENCRYPTION_KEY")
    @classmethod
    def _validate_field_enc_key(cls, v: str) -> str:
        if v and len(v) != 64:
            raise ValueError("FIELD_ENCRYPTION_KEY must be 64 hex characters (32 bytes)")
        if v:
            try:
                bytes.fromhex(v)
            except ValueError as exc:
                raise ValueError("FIELD_ENCRYPTION_KEY must be valid hex") from exc
        return v

    @field_validator("SECRETS_MASTER_KEY")
    @classmethod
    def _validate_master_key(cls, v: str) -> str:
        env = os.getenv("APP_ENV", "development")
        if env == "production" and not v:
            raise ValueError("P11-CFG-1: SECRETS_MASTER_KEY is required in production")
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = PhaseConfig()
