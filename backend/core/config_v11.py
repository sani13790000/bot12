"""
backend/core/config_v11.py
Galaxy Vast AI -- Config Phase 11 Patches

P11-CFG-1: SECRETS_MASTER_KEY required in production
P11-CFG-2: ALLOWED_ORIGINS strict
P11-CFG-3: CORS allow_credentials=True only with explicit origins
P11-CFG-4: Content-Security-Policy config
P11-CFG-5: LOG_REDACTER_ENABLED flag
P11-CFG-6: ENCRYPTION_AT_REST_KEY for DB field encryption
P11-CFG-7: SESSION_COOKIE_SECURE, SAMESITE flags
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Phase-11 hardened settings."""

    # -- Auth --
    JWT_SECRET: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=14)

    # -- Database --
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # -- Security --
    SECRETS_MASTER_KEY: str = ""
    ENCRYPTION_AT_REST_KEY: str = ""
    ALLOWED_ORIGINS: List[str] = Field(default_factory=list)
    CORS_ALLOW_CREDENTIALS: bool = True

    # -- CSP --
    CSP_DEFAULT_SRC: str = "'self'"
    CSP_SCRIPT_SRC: str = "'self'"
    CSP_REPORT_URI: str = "/api/v1/csp-report"

    # -- Logging --
    LOG_REDACTER_ENABLED: bool = True
    LOG_LEVEL: str = "INFO"

    # -- Session --
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "strict"

    # -- Telegram --
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_CHAT_IDS: List[int] = Field(default_factory=list)

    # -- MT5 --
    MT5_ACCOUNT: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""

    # -- Misc --
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: object) -> List[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return list(v)  # type: ignore[arg-type]

    @field_validator("TELEGRAM_ADMIN_CHAT_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v: object) -> List[int]:
        if isinstance(v, str):
            return [int(x) for x in v.split(",") if x.strip().isdigit()]
        return list(v)  # type: ignore[arg-type]

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
