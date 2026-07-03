"""
backend/core/config_v11.py -- Phase-E fix

E-5: JWT_SECRET was hardcoded 'change-me-in-production'
     Now reads from JWT_SECRET env var with validation on startup.
E-6: All security settings read from environment variables.
"""
from __future__ import annotations

import os
import secrets


class SecurityConfig:
    """
    Security settings loaded from environment variables.

    Required env vars in production:
      JWT_SECRET        - min 32 char random string
      BCRYPT_ROUNDS     - int (default 12)

    Generate JWT_SECRET:
      python -c "import secrets; print(secrets.token_hex(32))"
    """

    # JWT settings
    JWT_SECRET: str = os.environ.get("JWT_SECRET", "")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))
    JWT_REFRESH_EXPIRE_DAYS: int = int(os.environ.get("JWT_REFRESH_EXPIRE_DAYS", "30"))

    # Password hashing
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

    # Audit
    AUDIT_LOG_ENABLED: bool = (
        os.environ.get("AUDIT_LOG_ENABLED", "true").lower() == "true"
    )
    SESSION_COOKIE_SECURE: bool = (
        os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"
    )
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = os.environ.get("SESSION_COOKIE_SAMESITE", "lax")

    @classmethod
    def validate(cls) -> None:
        """
        Validate security settings at startup.
        In production: raises ValueError if JWT_SECRET is missing or too short.
        In development: generates ephemeral key and logs a warning.
        """
        env = os.environ.get("APP_ENV", "development").lower()

        if not cls.JWT_SECRET:
            if env == "production":
                raise ValueError(
                    "JWT_SECRET environment variable is required in production. "
                    "Generate: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            # Development only: generate ephemeral key
            cls.JWT_SECRET = secrets.token_hex(32)
            import logging
            logging.getLogger(__name__).warning(
                "JWT_SECRET not set - using ephemeral random key. "
                "Sessions will be invalidated on restart. "
                "Add JWT_SECRET to your .env file."
            )
            return

        if len(cls.JWT_SECRET) < 32:
            raise ValueError(
                f"JWT_SECRET is too short ({len(cls.JWT_SECRET)} chars). "
                "Minimum 32 characters required."
            )

    @classmethod
    def get_jwt_secret(cls) -> str:
        """Always-validated getter for use in auth middleware."""
        if not cls.JWT_SECRET:
            cls.validate()
        return cls.JWT_SECRET


security_config = SecurityConfig()

__all__ = ["SecurityConfig", "security_config"]
