"""Application settings — loaded from environment variables.

All REQUIRED fields will cause sys.exit(1) with a clear error message if missing.
This is intentional: we never start with a broken config.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── App ──
    APP_VERSION: str  = Field(default="2.0.0", env="APP_VERSION")
    ENVIRONMENT: str  = Field(default="development", env="ENVIRONMENT")
    PORT: int         = Field(default=8000, env="PORT")

    # ── Supabase (REQUIRED) ───────────────────────────────────────────────────
    SUPABASE_URL:             str = Field(..., env="SUPABASE_URL")
    SUPABASE_ANON_KEY:        str = Field(..., env="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., env="SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_DB_URL:          str = Field(..., env="SUPABASE_DB_URL")

    # ── Security (REQUIRED) ──────────────────────────────────────────────────
    JWT_SECRET_KEY:   str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM:    str = Field(default="HS256", env="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    # ── License (REQUIRED) ─────────────────────────────────────────────────
    LICENSE_ENCRYPTION_KEY: str = Field(..., env="LICENSE_ENCRYPTION_KEY")
    LICENSE_SIGNATURE_KEY:  str = Field(..., env="LICENSE_SIGNATURE_KEY")
    # LICENSE_SALT is now REQUIRED — no hardcoded default (security fix)
    LICENSE_SALT: str = Field(..., env="LICENSE_SALT")

    # ── MT5 (optional — bot works without live trading) ──────────────────────
    MT5_LOGIN:    Optional[int] = Field(default=None, env="MT5_LOGIN")
    MT5_PASSWORD: Optional[str] = Field(default=None, env="MT5_PASSWORD")
    MT5_SERVER:   Optional[str] = Field(default=None, env="MT5_SERVER")

    # ── Trading Defaults ────────────────────────────────────────────────────
    DEFAULT_SYMBOL:            str   = Field(default="XAUUSD", env="DEFAULT_SYMBOL")
    DEFAULT_TIMEFRAME:         str   = Field(default="M15", env="DEFAULT_TIMEFRAME")
    DEFAULT_RISK_PERCENT:      float = Field(default=1.0, env="DEFAULT_RISK_PERCENT")
    MAX_DAILY_LOSS_PERCENT:    float = Field(default=3.0, env="MAX_DAILY_LOSS_PERCENT")
    MAX_OPEN_TRADES:           int   = Field(default=3, env="MAX_OPEN_TRADES")
    MIN_CONFIDENCE_THRESHOLD:  float = Field(default=0.55, env="MIN_CONFIDENCE_THRESHOLD")
    MIN_VOTE_SCORE:            float = Field(default=65.0, env="MIN_VOTE_SCORE")

    # ── Telegram (optional) ────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_ADMIN_IDS: str           = Field(default="", env="TELEGRAM_ADMIN_IDS")

    # ── Redis ──────────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(default="redis://redis:6379/0", env="REDIS_URL")

    # ── Sentry (optional) ───────────────────────────────────────────────────
    SENTRY_DSN: Optional[str] = Field(default=None, env="SENTRY_DSN")

    # ── CORS ──────────────────────────────────────────────────────────────────
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8501"],
        env="ALLOWED_ORIGINS",
    )

    # ── Misc ──────────────────────────────────────────────────────────────────
    LOG_LEVEL:                  str = Field(default="INFO", env="LOG_LEVEL")
    ML_RETRAIN_INTERVAL_HOURS:  int = Field(default=24, env="ML_RETRAIN_INTERVAL_HOURS")
    BACKTEST_MAX_WORKERS:       int = Field(default=4, env="BACKTEST_MAX_WORKERS")
    DASHBOARD_PORT:             int = Field(default=8501, env="DASHBOARD_PORT")

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters. Generate with: python3 -c 'import secrets; print(secrets.token_hex(32))'")
        return v

    @field_validator("ENVIRONMENT")
    @classmethod
    def environment_must_be_valid(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {allowed}")
        return v

    @property
    def telegram_admin_ids_list(self) -> List[int]:
        if not self.TELEGRAM_ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.TELEGRAM_ADMIN_IDS.split(",") if x.strip()]

    model_config = {"env_file": ".env", "case_sensitive": True, "extra": "ignore"}


# ── Singleton ─────────────────────────────────────────────────────────────────
try:
    settings = Settings()
except Exception as exc:
    import sys
    print(f"\n{'='*60}")
    print("GALAXY VAST CONFIG ERROR — Cannot start without required env vars")
    print(f"{'='*60}")
    print(str(exc))
    print(f"{'='*60}")
    print("Copy .env.example to .env and fill in all REQUIRED fields.")
    print(f"{'='*60}\n")
    sys.exit(1)
