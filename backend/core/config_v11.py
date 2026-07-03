"""backend/core/config_v11.py — Phase 11 Settings"""
from __future__ import annotations
from typing import Any
import os

class Settings:
    ENVIRONMENT: str = "development"
    JWT_SECRET_KEY: str = ""
    SECRETS_MASTER_KEY: str = ""
    FIELD_ENCRYPTION_KEY: str = ""
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000"]
    DEBUG: bool = False

    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)
        self._validate()

    def _validate(self) -> None:
        env = getattr(self, "ENVIRONMENT", "development")
        jwt = getattr(self, "JWT_SECRET_KEY", "")
        master = getattr(self, "SECRETS_MASTER_KEY", "")
        field_enc = getattr(self, "FIELD_ENCRYPTION_KEY", "")
        origins = getattr(self, "ALLOWED_ORIGINS", [])
        if env in ("staging", "production") and len(jwt) < 32:
            raise ValueError("JWT_SECRET_KEY must be >= 32 chars in staging/production")
        if env == "production" and not master:
            raise ValueError("SECRETS_MASTER_KEY required in production")
        if master and len(master) < 8:
            raise ValueError("SECRETS_MASTER_KEY too short")
        if field_enc and len(field_enc) != 64:
            raise ValueError("FIELD_ENCRYPTION_KEY must be 64 hex chars")
        if env in ("staging", "production"):
            for o in origins:
                if o == "*":
                    raise ValueError("Wildcard origin not allowed in staging/production")
                if o not in ("*",) and not o.startswith("http"):
                    raise ValueError(f"Invalid origin format: {o}")

    def cors_allow_credentials(self) -> bool:
        return "*" not in getattr(self, "ALLOWED_ORIGINS", [])

    def get_csp_policy(self, nonce: str = "") -> str:
        parts = ["default-src 'self'", "frame-ancestors 'none'"]
        if nonce:
            parts.append(f"script-src 'self' 'nonce-{nonce}'")
        return "; ".join(parts)

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings(
            ENVIRONMENT=os.environ.get("ENVIRONMENT", "development"),
            JWT_SECRET_KEY=os.environ.get("JWT_SECRET_KEY", ""),
            SECRETS_MASTER_KEY=os.environ.get("SECRETS_MASTER_KEY", ""),
            FIELD_ENCRYPTION_KEY=os.environ.get("FIELD_ENCRYPTION_KEY", ""),
            ALLOWED_ORIGINS=os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(","),
        )
    return _settings

__all__ = ["Settings", "get_settings"]
