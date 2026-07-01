"""
backend/core/config_v11.py
Galaxy Vast AI — Config Phase 11
"""
from __future__ import annotations
import logging
from typing import List, Optional
from pydantic import Field
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings
logger = logging.getLogger(__name__)

class Settings(BaseSettings):
    ENVIRONMENT: str = Field(default="development")
    JWT_SECRET_KEY: str = Field(default="change-me-in-production-must-be-32-chars")
    SECRETS_MASTER_KEY: str = Field(default="")
    FIELD_ENCRYPTION_KEY: str = Field(default="")
    ALLOWED_ORIGINS: List[str] = Field(default=["http://localhost:3000"])
    DEBUG: bool = Field(default=False)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=30)
    BCRYPT_ROUNDS: int = Field(default=12)
    class Config:
        env_file = ".env"
        extra = "ignore"
    def cors_allow_credentials(self) -> bool:
        return "*" not in self.ALLOWED_ORIGINS
    def get_csp_policy(self, nonce: str = "") -> str:
        n = f" 'nonce-{nonce}'" if nonce else ""
        return f"default-src 'self'{n}; frame-ancestors 'none'; object-src 'none'"

_settings: Optional[Settings] = None
def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
