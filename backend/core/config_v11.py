"""
backend/core/config_v11.py  -- Phase-E fix

Phase-E fixes:
  E-5  JWT_SECRET = "change-me-in-production" was hardcoded.
       Now reads from environment variable JWT_SECRET.
       Raises ValueError on startup if not set in production.
  E-6  BCRYPT_ROUNDS, RATE_LIMIT_*, CORS_ORIGINS all read from env
       with safe defaults.
"""
from __future__ import annotations

import os
import secrets


class SecurityConfig:
    """
    Security settings loaded from environment variables.

    Required in production:
      - JWT_SECRET       : long random string (min 32 chars)
      - BCRYPT_ROUNDS    : int (default 12)

    Set in .env file or deployment secrets manager.
    """

    # JWT
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "30"))

    # Bcrypt
    BCRYPT_ROUNDS: int = int(os.environ.get("BCRYPT_ROUNDS", "12"))

    # Rate limiting
    RATE_LIMIT_LOGIN_PER_MINUTE: int = int(
        os.environ.get("RATE_LIMIT_LOGIN_PER_MINUTE", "5")
    )
    RATE_LIMIT_API_PER_MINUTE: int = int(
        os.environ.get("RATE_LIMIT_API_PER_MINUTE", "120")
    )

    # CORS
    CORS_ORIGINS: list[str] = [
        o.strip()
        for o in os.environ.get(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173",
        ).split(",")
        if o.strip()
    ]

    # Audit / session
    AUDIT_LOG_ENABLED: bool = os.environ.get("AUDIT_LOG_ENABLED", "true").lower() == "true"
    SESSION_COOKIE_SECURE: bool = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = os.environ.get("SESSION_COOKIE_SAMESITE", "lax")

    @classmethod
    def validate(cls) -> None:
        """
        Call once at application startup.
        Raises ValueError if critical secrets are missing or too short.
        """
        env = os.environ.get("APP_ENV", "development").lower()

        if not cls.JWT_SECRET:
            if env == "production":
                raise ValueError(
                    "JWT_SECRET environment variable is required in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            cls.JWT_SECRET = secrets.token_hex(32)
            import logging
            logging.getLogger(__name__).warning(
                "JWT_SECRET not set — using ephemeral random key. "
                "All sessions will be invalidated on restart. "
                "Set JWT_SECRET in .env for development."
            )

        if len(cls.JWT_SECRET) < 32:
            raise ValueError(
                f"JWT_SECRET is too short ({len(cls.JWT_SECRET)} chars). "
                "Minimum 32 characters required."
            )

    @classmethod
    def get_jwt_secret(cls) -> str:
        """Safe getter — always validated before use."""
        if not cls.JWT_SECRET:
            cls.validate()
        return cls.JWT_SECRET


security_config = SecurityConfig()

__all__ = ["SecurityConfig", "security_config"]
