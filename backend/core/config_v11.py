"""
backend/core/config_v11.py
Galaxy Vast AI - Config Phase 11: Security Hardening

Phase 11 adds security-focused configuration:
- Bcrypt rounds, JWT config, rate limiting, CORS origins, audit settings.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings
from typing import Optional


class SecurityConfig(BaseSettings):
    """Phase 11 security configuration."""

    BCRYPT_ROUNDS: int = 12
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 20
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    CORS_ALLOW_CREDENTIALS: bool = True
    AUDIT_LOG_ENABLED: bool = True
    AUDIT_RETENTION_DAYS: int = 90
    MASTER_KEY_ENV: str = "MT5_MASTER_KEY"
    DEK_ROTATION_DAYS: int = 30
    FORCE_HTTPS: bool = False
    HSTS_MAX_AGE: int = 63072000

    class Config:
        env_prefix = "SECURITY_"
        case_sensitive = False


security_config = SecurityConfig()
