"""backend/core/config_v11.py — Phase I Production Hardening
Fixes:
  I-1: ALLOWED_ORIGINS alias added (main.py needs it)
  I-2: REDIS_URL added
  I-3: TRUSTED_HOSTS added
  I-4: APP_ENV validation
  I-5: all required env vars documented
"""
from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from typing import List

log = logging.getLogger(__name__)


class Settings:
    # JWT
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "30"))

    # Auth
    BCRYPT_ROUNDS: int = int(os.environ.get("BCRYPT_ROUNDS", "12"))

    # Rate Limiting
    RATE_LIMIT_LOGIN_PER_MINUTE: int = int(
        os.environ.get("RATE_LIMIT_LOGIN_PER_MINUTE", "5")
    )
    RATE_LIMIT_API_PER_MINUTE: int = int(
        os.environ.get("RATE_LIMIT_API_PER_MINUTE", "120")
    )

    # CORS — I-1: both CORS_ORIGINS and ALLOWED_ORIGINS supported
    CORS_ORIGINS: List[str] = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173",
        ).split(",")
        if o.strip()
    ]

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """I-1: alias for main.py which uses ALLOWED_ORIGINS"""
        return self.CORS_ORIGINS

    # Trusted Hosts — I-3
    TRUSTED_HOSTS: List[str] = [
        h.strip()
        for h in os.environ.get(
            "TRUSTED_HOSTS",
            "localhost,127.0.0.1",
        ).split(",")
        if h.strip()
    ]

    # Redis — I-2: for distributed rate limiting (optional)
    REDIS_URL: str = os.environ.get("REDIS_URL", "")

    # Database
    SUPABASE_URL: str = os.environ.get("SUPABASE_URL", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    # App
    APP_ENV: str = os.environ.get("APP_ENV", "development").lower()
    APP_VERSION: str = os.environ.get("APP_VERSION", "2.0.0")
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

    # MT5
    MT5_GATEWAY_URL: str = os.environ.get("MT5_GATEWAY_URL", "http://localhost:8080")
    MT5_DEMO_MODE: bool = os.environ.get("MT5_DEMO_MODE", "true").lower() == "true"
    MT5_GATEWAY_TIMEOUT: int = int(os.environ.get("MT5_GATEWAY_TIMEOUT", "10"))

    # License
    LICENSE_SECRET: str = os.environ.get("LICENSE_SECRET", "")

    # Telegram
    TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_IDS: List[int] = [
        int(i.strip())
        for i in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",")
        if i.strip().isdigit()
    ]

    @classmethod
    def validate(cls) -> None:
        """I-4: run at startup — raises ValueError in production if missing."""
        env = os.environ.get("APP_ENV", "development").lower()

        if not cls.JWT_SECRET:
            if env == "production":
                raise ValueError(
                    "JWT_SECRET environment variable is required in production. "
                    'Run: python -c "import secrets; print(secrets.token_hex(32))"'
                )
            cls.JWT_SECRET = secrets.token_hex(32)
            log.warning(
                "JWT_SECRET not set - using ephemeral random key. "
                "Sessions will be invalidated on restart. "
                "Add JWT_SECRET to your .env file."
            )
        elif len(cls.JWT_SECRET) < 32:
            raise ValueError(
                f"JWT_SECRET is too short ({len(cls.JWT_SECRET)} chars). "
                "Minimum 32 chars required."
            )

        if env == "production":
            if not cls.SUPABASE_URL:
                raise ValueError("SUPABASE_URL is required in production")
            if not cls.SUPABASE_SERVICE_ROLE_KEY:
                raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required in production")
            if not cls.TELEGRAM_BOT_TOKEN:
                raise ValueError("TELEGRAM_BOT_TOKEN is required in production")
            if cls.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]:
                log.warning("CORS_ORIGINS still set to localhost defaults in production!")

        log.info(
            "Config validated env=%s jwt_len=%d cors=%s mt5_demo=%s",
            env, len(cls.JWT_SECRET), cls.CORS_ORIGINS, cls.MT5_DEMO_MODE,
        )

    @classmethod
    def get_jwt_secret(cls) -> str:
        if not cls.JWT_SECRET:
            cls.validate()
        return cls.JWT_SECRET


_settings_instance: Settings | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
    return _settings_instance


# Backward-compat singleton
settings = Settings()
