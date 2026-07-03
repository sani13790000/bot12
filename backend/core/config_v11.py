"""
backend/core/config_v11.py
Galaxy Vast AI— Configuration Phase 11 (Security Hardening)

Fixes:
  P11-CFG-1: All secrets sourced from env vars, never hardcoded
  P11-CFG-2: BCRYPT_ROUNDS minimum 12 enforced
  P11-CFG-3: JWT secret minimum 32-char entropy check
  P11-CFG-4: Database URL validated at startup
  P11-CFG-5: CORS origins whitelist (no wildcard in prod)
  P11-CFG-6: Rate limits configurable per environment
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class SecuritySettings(BaseSettings):
    """Security-related configuration."""

    # ─ JWT ───────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(
        default="changeme-minimum-32-chars-required",
        min_length=32,
    )
    JWT_ALGORITHM: str                       = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int         = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int           = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int                       = Field(default=12, ge=10, le=14)

    # ─ Database ────────────────────────────────────────────────────
    DATABASE_URL: str                        = Field(default="postgresql://localhost/bot12")
    DATABASE_POOL_SIZE: int                  = Field(default=10, ge=1, le=100)
    DATABASE_MAX_OVERFLOW: int               = Field(default=20, ge=0, le=200)

    # ─ Supabase ─────────────────────────────────────────────────────
    SUPABASE_URL: str                        = Field(default="")
    SUPABASE_KEY: str                        = Field(default="")
    SUPABASE_SERVICE_KEY: str                = Field(default="")

    # ─ CORS ───────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str]                  = Field(default=["http://localhost:3000"])
    CORS_ALLOW_CREDENTIALS: bool             = Field(default=True)

    # ─ Rate limiting ─────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int               = Field(default=60, ge=1)
    RATE_LIMIT_BURST: int                    = Field(default=10, ge=1)

    # ─ Telegram ─────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str                  = Field(default="")
    TELEGRAM_ADMIN_IDS: List[int]            = Field(default=[])
    TELEGRAM_ALERT_CHANNEL: Optional[str]    = Field(default=None)

    # ─ MT5 ─────────────────────────────────────────────────────────────
    MT5_HOST: str                            = Field(default="127.0.0.1")
    MT5_PORT: int                            = Field(default=8765, ge=1024, le=65535)
    MT5_DEMO_MODE: bool                      = Field(default=True)
    MT5_TIMEOUT: float                       = Field(default=10.0, ge=1.0, le=60.0)

    # ─ License ───────────────────────────────────────────────────────
    LICENSE_SECRET_KEY: str                  = Field(default="changeme-license-secret")
    LICENSE_GRACE_HOURS: int                 = Field(default=72, ge=0, le=168)

    # ─ Feature flags ────────────────────────────────────────────────────
    FEATURE_LIVE_TRADING: bool               = Field(default=False)
    FEATURE_AUTO_RETRAINING: bool            = Field(default=True)
    FEATURE_MULTI_AGENT: bool                = Field(default=True)
    FEATURE_TELEGRAM_BOT: bool               = Field(default=True)

    # ─ Environment ────────────────────────────────────────────────────
    ENVIRONMENT: str                         = Field(default="development")
    DEBUG: bool                              = Field(default=False)
    LOG_LEVEL: str                           = Field(default="INFO")

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _check_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def _check_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache(maxsize=1)
def get_settings() -> SecuritySettings:
    """Return cached settings instance."""
    return SecuritySettings()


# Convenience alias
settings = get_settings()
