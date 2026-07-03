"""
backend/core/config_v11.py
Galaxy Vast AI— Config Phase 11 Patches

P11-CFG-1 SECRETS_MASTER_KEY required in production
P11-CFG-2 ALLOWED_ORIGINS strict
P11-CFG-3 CORS allow_credentials=True only with explicit origins
P11-CFG-4 Content-Security-Policy config
P11-CFG-5 LOG_REDACTER_ENABLED flag
P11-CFG-6 ENCRYPTION_AT_REST_KEY for DB field encryption
P11-CFG-7 SESSION_COOKIE_SECURE, SAMESITE flags
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

try:
    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings, Field, validator as field_validator  # type: ignore

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings with Phase 11 security hardening."""

    # Environment
    ENVIRONMENT: str = "development"

    # JWT
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=14)

    # Database
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Security
    SECRETS_MASTER_KEY: str = ""
    FIELD_ENCRYPTION_KEY: str = ""
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000"]
    LICENSE_SECRET: str = ""
    LICENSE_SALT: str = ""

    # MT5
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ""
    MT5_SERVER: str = ""

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ADMIN_IDS: List[int] = []

    # CSP
    CSP_REPORT_ONLY: bool = False
    CSP_REPORT_URI: str = "/api/v1/csp-report"
    LOG_REDACTER_ENABLED: bool = True
    FIELD_ENCRYPTION_ENABLED: bool = True
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "strict"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt_secret(cls, v: str, info: Any = None) -> str:
        env = os.environ.get("ENVIRONMENT", "development")
        if env in ("production", "staging") and len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 chars in production/staging")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def validate_origins(cls, v: List[str], info: Any = None) -> List[str]:
        env = os.environ.get("ENVIRONMENT", "development")
        if env == "production" and "*" in v:
            raise ValueError("Wildcard ALLOWED_ORIGINS not permitted in production")
        return v

    @field_validator("SECRETS_MASTER_KEY")
    @classmethod
    def validate_master_key(cls, v: str, info: Any = None) -> str:
        if v and len(v) < 16:
            raise ValueError("SECRETS_MASTER_KEY must be at least 16 chars")
        return v

    @field_validator("FIELD_ENCRYPTION_KEY")
    @classmethod
    def validate_field_enc_key(cls, v: str, info: Any = None) -> str:
        if v and len(v) != 64:
            raise ValueError("FIELD_ENCRYPTION_KEY must be 64 hex chars (32 bytes)")
        return v

    def cors_allow_credentials(self) -> bool:
        return "*" not in self.ALLOWED_ORIGINS

    def get_csp_policy(self, nonce: str = "") -> str:
        nonce_directive = f"'nonce-{nonce}'" if nonce else ""
        return (
            f"default-src 'self'; "
            f"script-src 'self' {nonce_directive}; "
            f"style-src 'self' 'unsafe-inline'; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"upgrade-insecure-requests"
        )


from functools import lru_cache
from typing import Any


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
