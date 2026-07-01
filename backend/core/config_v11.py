"""
backend/core/config_v11.py
Galaxy Vast AI— Config Phase 11 Patches
"""
from __future__ import annotations

import os
import re
from typing import List, Optional

try:
    from pydantic import Field, field_validator
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings, Field, validator as field_validator


class Settings(BaseSettings):
    ENVIRONMENT: str = 'development'
    JWT_SECRET_KEY: str = ''
    SECRETS_MASTER_KEY: str = ''
    FIELD_ENCRYPTION_KEY: str = ''
    ALLOWED_ORIGINS: List[str] = ['http://localhost:3000']
    DATABASE_URL: str = ''
    SUPABASE_URL: str = ''
    SUPABASE_SERVICE_KEY: str = ''
    MT5_LOGIN: int = 0
    MT5_PASSWORD: str = ''
    MT5_SERVER: str = ''
    TELEGRAM_BOT_TOKEN: str = ''
    TELEGRAM_ADMIN_IDS: str = ''
    LOG_LEVEL: str = 'INFO'
    LOG_REDACTER_ENABLED: bool = True
    OTEL_SDK_DISABLED: bool = True
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS: int = Field(default=12, ge=10, le=14)
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = 'strict'
    CSP_REPORT_ONLY: bool = False
    CSP_REPORT_URI: str = '/api/v1/csp-report'

    model_config = {'env_file': '.env', 'env_file_encoding': 'utf-8', 'extra': 'ignore'}

    def cors_allow_credentials(self) -> bool:
        return '*' not in self.ALLOWED_ORIGINS

    def get_csp_policy(self, nonce: str = '') -> str:
        nd = f"'nonce-{nonce}'" if nonce else ''
        return (
            f"default-src 'self'; "
            f"script-src 'self' {nd}; "
            "frame-ancestors 'none'"
        )


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
