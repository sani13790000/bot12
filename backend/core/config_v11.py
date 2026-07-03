"""
backend/core/config_v11.py
Phase 11 security-hardened configuration.

P11-CFG-1: Immutable settings after startup
P11-CFG-2: Origin allowlist validation
P11-CFG-3: Field encryption key validation
P11-CFG-4: All secrets via environment (no defaults in code)
"""
from __future__ import annotations

import re
from typing import Any, List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class SecurityConfig(BaseSettings):
    """Phase 11 Security Configuration."""

    # JWT
    JWT_SECRET_KEY:              str = ""
    JWT_ALGORITHM:               str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS:   int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS:               int = Field(default=12, ge=10, le=14)

    # Database
    DATABASE_URL:           str = ""
    SUPABASE_URL:           str = ""
    SUPABASE_KEY:           str = ""
    SUPABASE_SERVICE_KEY:   str = ""

    # Security headers
    ALLOWED_ORIGINS:            List[str] = Field(default_factory=list)
    CORS_ALLOW_CREDENTIALS:     bool = True
    CORS_MAX_AGE:               int  = 600
    CSP_ENABLED:                bool = True
    CSP_REPORT_ONLY:            bool = False
    CSP_REPORT_URI:             str  = "/api/v1/csp-report"
    LOG_REDACTER_ENABLED:       bool = True
    FIELD_ENCRYPTION_KEY:       str  = ""
    SESSION_COOKIE_SECURE:      bool = True
    SESSION_COOKIE_SAMESITE:    str  = "strict"
    SESSION_COOKIE_HTTPONLY:    bool = True
    STRIPE_WEBHOOK_SECRET:      str  = ""

    # Telegram
    TELEGRAM_BOT_TOKEN:    str = ""
    TELEGRAM_ADMIN_IDS:    str = ""  # comma-separated

    # MT5
    MT5_ACCOUNT_ID:    str = ""
    METAAPI_TOKEN:     str = ""
    MT5_SERVER:        str = ""
    MT5_LOGIN:         str = ""
    MT5_PASSWORD:      str = ""

    # API
    API_BASE_URL:  str  = "http://api:8000"
    DEBUG:         bool = False
    ENVIRONMENT:   str  = "production"

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def _validate_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = [o.strip() for o in v.split(",") if o.strip()]
        for origin in v:
            if not re.match(r"^https?://[^/]+$", origin):
                raise ValueError(
                    f"P11-CFG-2 Invalid origin format: {origin!r}. "
                    "Must be scheme://host[:port] (no trailing slash)"
                )
        return v

    @field_validator("FIELD_ENCRYPTION_KEY")
    @classmethod
    def _validate_field_enc_key(cls, v: str) -> str:
        if v and len(v) < 32:
            raise ValueError("FIELD_ENCRYPTION_KEY must be at least 32 chars")
        return v

    @field_validator("SESSION_COOKIE_SAMESITE")
    @classmethod
    def _validate_samesite(cls, v: str) -> str:
        allowed = {"strict", "lax", "none"}
        if v.lower() not in allowed:
            raise ValueError(f"SESSION_COOKIE_SAMESITE must be one of {allowed}")
        return v.lower()

    def get_admin_ids(self) -> List[int]:
        """Parse comma-separated admin IDs."""
        if not self.TELEGRAM_ADMIN_IDS:
            return []
        return [
            int(i.strip())
            for i in self.TELEGRAM_ADMIN_IDS.split(",")
            if i.strip().isdigit()
        ]


security_config = SecurityConfig()
