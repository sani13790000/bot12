"""
ØªÙØ¸ÛÙØ§Øª ÙØ±Ú©Ø²Û Ø³ÛØ³ØªÙ

Ø§ÛÙ ÙØ§ÛÙ ØªÙØ§Ù ØªÙØ¸ÛÙØ§Øª ÙØ§Ø¨Ù Ù¾ÛÚ©Ø±Ø¨ÙØ¯Û Ø±Ø§ ÙØ¯ÛØ±ÛØª ÙÛâÚ©ÙØ¯.
ØªÙØ¸ÛÙØ§Øª Ø§Ø² ÙØªØºÛØ±ÙØ§Û ÙØ­ÛØ·Û (environment variables) Ø®ÙØ§ÙØ¯Ù ÙÛâØ´ÙÙØ¯.
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field
from functools import lru_cache


class Settings(BaseSettings):
    """
    ØªÙØ¸ÛÙØ§Øª Ø§ØµÙÛ Ø³ÛØ³ØªÙ

    ØªÙØ§Ù ØªÙØ¸ÛÙØ§Øª Ø§Ø² ÙØ§ÛÙ .env ÛØ§ ÙØªØºÛØ±ÙØ§Û ÙØ­ÛØ·Û Ø®ÙØ§ÙØ¯Ù ÙÛâØ´ÙÙØ¯.
    """

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª Ø¹ÙÙÙÛ
    # =====================================================
    APP_NAME: str = "MT5 Trading Ecosystem"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª API
    # =====================================================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª Supabase (Ø¯ÛØªØ§Ø¨ÛØ³)
    # =====================================================
    SUPABASE_URL: str = Field(..., env="SUPABASE_URL")
    SUPABASE_ANON_KEY: str = Field(..., env="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., env="SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_DB_URL: str = Field(..., env="SUPABASE_DB_URL")

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª JWT
    # =====================================================
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª ØªÙÚ¯Ø±Ø§Ù
    # =====================================================
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª ÙØ§ÛØ³ÙØ³
    # =====================================================
    LICENSE_ENCRYPTION_KEY: str = Field(..., env="LICENSE_ENCRYPTION_KEY")
    LICENSE_SIGNATURE_KEY: str = Field(..., env="LICENSE_SIGNATURE_KEY")

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª ØªØ­ÙÛÙ Ø¨Ø§Ø²Ø§Ø±
    # =====================================================
    SYMBOLS_SUPPORTED: List[str] = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]
    DEFAULT_SYMBOL: str = "XAUUSD"
    DEFAULT_TIMEFRAMES: List[str] = ["M15", "H1", "H4", "D1"]

    # Ø§ÙØªÛØ§Ø²Ø¯ÙÛ
    MIN_ENTRY_SCORE: float = 65.0
    EXCELLENT_SCORE: float = 85.0
    GOOD_SCORE: float = 75.0
    MODERATE_SCORE: float = 65.0

    # ÙØ²ÙâÙØ§Û Ø§ÙØªÛØ§Ø²Ø¯ÙÛ
    SMC_WEIGHT: float = 0.30
    PRICE_ACTION_WEIGHT: float = 0.25
    LIQUIDITY_WEIGHT: float = 0.15
    MTF_WEIGHT: float = 0.10
    SESSION_WEIGHT: float = 0.10
    VOLATILITY_WEIGHT: float = 0.10

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª Ø±ÛØ³Ú©
    # =====================================================
    MAX_RISK_PER_TRADE: float = 10.0  # Ø¯Ø±ØµØ¯
    MAX_DAILY_RISK: float = 20.0  # Ø¯Ø±ØµØ¯
    MAX_DAILY_TRADES: int = 50
    MAX_DRAWDOWN: float = 30.0  # Ø¯Ø±ØµØ¯

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª Ø³Ø´ÙâÙØ§Û ÙØ¹Ø§ÙÙØ§ØªÛ
    # =====================================================
    KILLZONE_LONDON_START: str = "08:00"
    KILLZONE_LONDON_END: str = "11:00"
    KILLZONE_NEWYORK_START: str = "13:30"
    KILLZONE_NEWYORK_END: str = "16:00"
    KILLZONE_TOKYO_START: str = "00:30"
    KILLZONE_TOKYO_END: str = "02:00"

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª ÙØ§Ú¯
    # =====================================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[str] = None

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª Redis (Ø§Ø®ØªÛØ§Ø±Û)
    # =====================================================
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")

    # =====================================================
    # ØªÙØ¸ÛÙØ§Øª CORS
    # =====================================================
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"])

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    Ø¯Ø±ÛØ§ÙØª ØªÙØ¸ÛÙØ§Øª (Ú©Ø´ Ø´Ø¯Ù)

    Ø§ÛÙ ØªØ§Ø¨Ø¹ Ø§Ø² lru_cache Ø§Ø³ØªÙØ§Ø¯Ù ÙÛâÚ©ÙØ¯ ØªØ§ ØªÙØ¸ÛÙØ§Øª ÙÙØ·
    ÛÚ© Ø¨Ø§Ø± Ø®ÙØ§ÙØ¯Ù Ø´ÙÙØ¯ Ù Ø¯Ø± Ø­Ø§ÙØ¸Ù Ø°Ø®ÛØ±Ù Ø´ÙÙØ¯.

    Returns:
        Settings: Ø´ÛØ¡ ØªÙØ¸ÛÙØ§Øª
    """
    return Settings()


# ÙÙÙÙÙ Ú¯ÙÙØ¨Ø§Ù Ø§Ø² ØªÙØ¸ÛÙØ§Øª
settings = get_settings()
