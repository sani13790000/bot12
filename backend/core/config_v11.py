"""
backend/core/config_v11.py
Galaxy Vast AI - Config Phase 11 Security Patches

P11-CFG-1: SECRETS_MASTER_KEY required in production
P11-CFG-2: ALLOWED_ORIGINS strict validation
P11-CFG-3: CORS credentials only with explicit origins
P11-CFG-4: Content-Security-Policy config
P11-CFG-5: LOG_REDACTER_ENABLED flag
P11-CFG-6: ENCRYPTION_AT_REST_KEY for DB field encryption
P11-CFG-7: SESSION_COOKIE_SECURE and SAMESITE flags
"""
from __future__ import annotations
import logging
import re
from typing import Any, List
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger    = logging.getLogger(__name__)
_ORIG_RE  = re.compile(r"^https?://[a-zA-Z0-9._-]+(:[0-9]+)?$")


class ConfigV11(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    JWT_SECRET_KEY:              str        = "changeme"
    JWT_ALGORITHM:               str        = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int        = 60
    REFRESH_TOKEN_EXPIRE_DAYS:   int        = 30
    BCRYPT_ROUNDS:               int        = 12
    DATABASE_URL:                str        = ""
    SUPABASE_URL:                str        = ""
    SUPABASE_KEY:                str        = ""
    SUPABASE_SERVICE_KEY:        str        = ""
    SECRETS_MASTER_KEY:          str        = ""
    ALLOWED_ORIGINS:             List[str]  = []
    CORS_ALLOW_CREDENTIALS:      bool       = False
    CSP_ENABLED:                 bool       = True
    CSP_REPORT_ONLY:             bool       = False
    CSP_REPORT_URI:              str        = "/api/v1/csp-report"
    LOG_REDACTER_ENABLED:        bool       = True
    FIELD_ENCRYPTION_KEY:        str        = ""
    SESSION_COOKIE_SECURE:       bool       = True
    SESSION_COOKIE_SAMESITE:     str        = "strict"
    LICENSE_SECRET_KEY:          str        = "changeme-license-secret"
    TELEGRAM_BOT_TOKEN:          str        = ""
    TELEGRAM_CHANNEL_ID:         str        = ""
    TELEGRAM_ADMIN_IDS:          List[int]  = []
    MT5_BRIDGE_URL:              str        = "http://localhost:8001"
    MT5_BRIDGE_TOKEN:            str        = ""
    MT5_DEMO_MODE:               bool       = True
    MAX_DAILY_LOSS_PCT:          float      = 5.0
    MAX_OPEN_TRADES:             int        = 5
    MAX_LOT_SIZE:                float      = 1.0
    KILL_SWITCH_DRAWDOWN_PCT:    float      = 10.0

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def validate_jwt(cls, v: str) -> str:
        import os
        if os.getenv("ENVIRONMENT") == "production" and v in ("changeme", ""):
            raise ValueError("JWT_SECRET_KEY must be set in production")
        if len(v) < 16:
            raise ValueError("JWT_SECRET_KEY must be >= 16 chars")
        return v

    @field_validator("SECRETS_MASTER_KEY")
    @classmethod
    def validate_master_key(cls, v: str) -> str:
        import os
        if os.getenv("ENVIRONMENT") == "production" and not v:
            raise ValueError("P11-CFG-1: SECRETS_MASTER_KEY required in production")
        return v

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def validate_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            v = [o.strip() for o in v.split(",") if o.strip()]
        for origin in v:
            if origin != "*" and not _ORIG_RE.match(origin):
                raise ValueError(f"P11-CFG-2 Invalid origin: {origin!r}")
        return list(v)

    @field_validator("FIELD_ENCRYPTION_KEY")
    @classmethod
    def validate_field_key(cls, v: str) -> str:
        if v and len(v) not in (16, 24, 32):
            raise ValueError("FIELD_ENCRYPTION_KEY must be 16, 24, or 32 bytes")
        return v

    @model_validator(mode="after")
    def check_cors(self) -> "ConfigV11":
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.ALLOWED_ORIGINS:
            raise ValueError("P11-CFG-3: CORS credentials=True requires explicit origins")
        return self


def get_config_v11() -> ConfigV11:
    return ConfigV11()
