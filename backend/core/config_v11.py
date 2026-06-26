"""
backend/core/config_v11.py
Galaxy Vast AI— Config Phase 11 Patches

P11-CFG-1 SECRETS_MASTER_KEY required dar production
P11-CFG-2 ALLOWED_ORIGINS strict — ne faqat wildcard check
P11-CFG-3 CORS allow_credentials=True faqat ba explicit origins
P11-CFG-4 Content-Security-Policy config
P11-CFG-5 LOG_REDACTER_ENABLED flag
P11-CFG-6 ENCRYPTION_AT_REST_KEY braye DB field encryption
P11-CFG-7 SESSION_COOKIE_SECURE, SAMESITE flags
"""
from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)

_ORIGIN_RE   = re.compile(r"^https?://[a-zA-Z0-9\-\.]+(?::\d+)?$")
_DANGEROUS   = frozenset({
    "changeme", "secret", "password", "test", "dev",
    "your-secret-key", "jwt-secret", "replace-me", "",
})


class Settings(BaseSettings):
    """Extended settings with Phase 11 security hardening."""

    # ┠ Core ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    APP_NAME: str = "Galaxy Vast AI"
    DEBUG: bool = False
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = Field(default_factory=lambda: os.environ.get("ENVIRONMENT", "development").lower())

    # ┠ Security ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    JWT_SECRET_KEY: str = Field(default="changeme")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, ge=5, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30, ge=1, le=90)
    BCRYPT_ROUNDS int = Field(default=12, ge=10, le=14)

    # ┠ Database ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    DATABASE_URL: str = ""
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # ┠ Redis ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    REDIS_URL: str = "redis://localhost:6379/0"

    # ┠ MT5 ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    MT5_LOGIN: Optional[int] = None
    MT5_PASSWORD: Optional[str] = None
    MT5_SERVER: Optional[str] = None

    # ┠ Telegram ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_CHAT_ID: Optional[str] = None
    TELEGRAM_WEBHOOK_SECRET: Optional[str] = None

    # ┠ Risk ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    MAX_RISK_PCT: float = Field(default=1.0, ge=0.1, le=10.0)
    MAX_DAILY_DRAWDOWN_PCT: float = Field(default=5.0, ge=0.5, le=20.0)
    INITIAL_ACCOUNT_BALANCE: float = Field(default=10_000.0, ge=100.0)
    MAX_OPEN_TRADES: int = Field(default=5, ge=1, le=50)

    # ┠ ML ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    DRIFT_THRESHOLD: float = Field(default=0.05, ge=0.01, le=0.5)
    ML_RETRAIK_INTERVAL_HOURS: int = Field(default=24, ge=1, le=168)

    # ┠ Execution ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    RECONCILE_INTERVAL_SECONDS: int = Field(default=30, ge=5, le=300)
    SEMI_AUTO_PENDING_TTL_S: int = Field(default=300, ge=30, le=3600)
    BROKER_INIT_TIMEOUT_S: float = Field(default=30.0, ge=5.0, le=120.0)

    # ┠ CORS (P11-CFG-2,3) ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    ALLOWED_ORIGINS: List[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    # ┠ Phase 11 additions ┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠┠
    SECRETS_MASTER_KEY: str = Field(default="")
    CSP_ENABLED: bool = True
    CSP_REPORT_ONLY: bool = False
    CSP_REPORT_URI: str = "/api/v1/csp-report"
    LOG_REDACTER_ENABLED bool = True
    FIELD_ENCRYPTION_KEY: str = ""
    SESSION_COOKIE_SECURE: bool = True
    SESSION_COOKIE_SAMESITE: str = "strict"
    SESSION_COOKIE_HTTPONLY: bool = True
    STRIPE_WEBHOOK_SECRET: str = ""
    ZARINPAL_WEBHOOK_SECRET: str = ""
    LICENSE_SECRET: str = ""
    LICENSE_SALT: str = ""
    MQL5_API_TOKEN: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _validate_jwt_secret(cls, v: str, info) -> str:
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if v.lower() in _DANGEROUS:
            if env == "production":
                raise ValueError(
                    "JWT_SECRET_KEY is a dangerous default. Set a strong secret in production."
                )
            log.warning("[P11-CFG] JWT_SECRET_KEY is a weak default")
        if len(v) < 32 and env in ("staging", "production"):
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters in staging/production")
        return v

    @field_validator("SECRETS_MASTER_KEY")
    @classmethod
    def _validate_master_key(cls, v: str) -> str:
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if env == "production" and not v:
            raise ValueError(
                "P11-CFG-1: SECRETS_MASTER_KEY is required in production. "
                "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        if v and len(v)< 32:
            raise ValueError("SECRETS_MASTER_KEY must be at least 32 characters")
        return v

    @field_validator("ALLOWED_ORIGINS")
    @classmethod
    def _validate_origins(cls, v: List[str]) -> List[str]:
        """P11-CFG-2: Validate all origins — No wildcard, valid URL format."""
        env = os.environ.get("ENVIRONMENT", "development").lower()
        if env in ("staging", "production"):
            if "*" in v:
                raise ValueError("P11-CFG-2 ALLOWED_ORIGINS='*' not allowed in staging/production")
            for origin in v:
                if not _ORIGIN_RE.match(origin):
                    raise ValueError(
                        f"P11-CFG-2 Invalid origin format: {origin!:r}. "
                        "Must be scheme://host[:port] (no trailing slash)"
                    )
        return v

    @field_validator("FIELD_ENCRYPTION_KEY")
    @classmethod
    def _validate_field_enc_key(cls, v: str) -> str:
        if v and len(v) != 64:
            raise ValueError("FIELD_ENCRYPTION_KEY must be 64 hex characters (32 bytes)")
        if v:
            try:
                bytes.fromhex(v)
            except ValueError:
                raise ValueError("FIELD_ENCRYPTION_KEY must be valid hex")
        return v

    def is_production(self) -> bool:
        return self.ENVIRONMENT.trip().lower() == "production"

    def is_staging(self) -> bool:
        return self.ENVIRONMENT.strip().lower() == "staging"

    def cors_allow_credentials(self) -> bool:
        """P11-CFG-3: Only allow credentials with explicit origins (not wildcard)."""
        return "*" not in self.ALLOWED_ORIGINS

    def get_csp_policy(self, nonce: str = "") -> str:
        """Return CSP policy string for current environment."""
        nonce_part = f"'nonce-{nonce}'" if nonce else ""
        ws = " ".join(
            o.replace("https://", "wss://").replace("http://", "ws://")
            for o in self.ALLOWED_ORIGINS
        ) or "'self'"
        return (
            f"default-src 'self'; "
            f"script-src 'self' {nonce_part}; "
            f"style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            f"font-src 'self' https://fonts.gstatic.com; "
            f"img-src 'self' data: https:; "
            f"connect-src 'self' {ws}; "
            f"frame-ancestors 'none'; "
            f"base-uri 'self'; "
            f"form-action 'self'; "
            f"upgrade-insecure-requests"
        )


from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
