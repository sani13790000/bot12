"""backend/core/config_patch.py — Phase T

T-25: JWT_SECRET_KEY default 'changeme' — dangerous in production
T-26: No DATABASE_URL validation at startup
T-27: ACCESS_TOKEN_EXPIRE_MINUTES no upper cap
T-28: CORS_ORIGINS accepts '*' wildcard in production
T-29: No environment detection
T-30: BCRYPT_ROUNDS not configurable
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

log = logging.getLogger(__name__)

_DANGEROUS_SECRETS = {"changeme", "secret", "password", "test", "dev", "your-secret-key", "jwt-secret", "replace-me"}
_ACCESS_TOKEN_MAX_MINUTES = 1440
_BCRYPT_ROUNDS_DEFAULT = 12
_BCRYPT_ROUNDS_MIN = 10
_BCRYPT_ROUNDS_MAX = 14


def _detect_environment() -> str:
    env = (os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or os.environ.get("FASTAPI_ENV") or "development").lower()
    if env in ("prod", "production"):
        return "production"
    if env in ("staging", "stage"):
        return "staging"
    return "development"


def is_production() -> bool:
    return _detect_environment() == "production"


def get_bcrypt_rounds() -> int:
    try:
        from backend.core.config import get_settings
        return getattr(get_settings(), "BCRYPT_ROUNDS", _BCRYPT_ROUNDS_DEFAULT)
    except Exception:
        return _BCRYPT_ROUNDS_DEFAULT


def validate_settings(settings) -> None:
    env = _detect_environment()
    log.info("Environment: %s", env)

    jwt_key = getattr(settings, "JWT_SECRET_KEY", "")
    if not jwt_key or jwt_key.lower() in _DANGEROUS_SECRETS:
        if env == "production":
            raise RuntimeError("FATAL: JWT_SECRET_KEY is set to a dangerous default. Set a strong random secret.")
        log.warning("JWT_SECRET_KEY is a dangerous default — acceptable only in development")

    if len(str(jwt_key)) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters")

    db_url = (getattr(settings, "DATABASE_URL", None) or getattr(settings, "SUPABASE_URL", None) or os.environ.get("SUPABASE_URL") or os.environ.get("DATABASE_URL"))
    if not db_url:
        raise RuntimeError("FATAL: No database URL configured. Set SUPABASE_URL or DATABASE_URL.")

    exp_min = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    if exp_min > _ACCESS_TOKEN_MAX_MINUTES:
        log.warning("ACCESS_TOKEN_EXPIRE_MINUTES=%d exceeds max %d — capping", exp_min, _ACCESS_TOKEN_MAX_MINUTES)
        try:
            settings.ACCESS_TOKEN_EXPIRE_MINUTES = _ACCESS_TOKEN_MAX_MINUTES
        except Exception:
            pass

    cors = getattr(settings, "CORS_ORIGINS", [])
    if isinstance(cors, str):
        cors = [cors]
    if "*" in cors:
        if env == "production":
            raise RuntimeError("FATAL: CORS_ORIGINS='*' is not allowed in production.")
        log.warning("CORS_ORIGINS='*' — acceptable only in development/testing")

    bcrypt_rounds = getattr(settings, "BCRYPT_ROUNDS", _BCRYPT_ROUNDS_DEFAULT)
    if not (_BCRYPT_ROUNDS_MIN <= bcrypt_rounds <= _BCRYPT_ROUNDS_MAX):
        log.warning("BCRYPT_ROUNDS=%d outside recommended range [%d, %d]", bcrypt_rounds, _BCRYPT_ROUNDS_MIN, _BCRYPT_ROUNDS_MAX)

    log.info("Settings validation passed (env=%s)", env)


def patch_config_at_startup() -> None:
    try:
        from backend.core.config import get_settings
        validate_settings(get_settings())
    except RuntimeError:
        raise
    except Exception as exc:
        log.error("Config validation error: %s", exc)
        if is_production():
            raise RuntimeError(f"Config validation failed in production: {exc}") from exc
