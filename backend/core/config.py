"""
تنظیمات مرکزی سیستم

این فایل تمام تنظیمات قابل پیکربندی را مدیریت می‌کند.
تنظیمات از متغیرهای محیطی (environment variables) خوانده می‌شوند.
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field
from functools import lru_cache


class Settings(BaseSettings):
    """
    تنظیمات اصلی سیستم

    تمام تنظیمات از فایل .env یا متغیرهای محیطی خوانده می‌شوند.
    """

    # =====================================================
    # تنظیمات عمومی
    # =====================================================
    APP_NAME: str = "MT5 Trading Ecosystem"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # =====================================================
    # تنظیمات API
    # =====================================================
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    API_PREFIX: str = "/api/v1"

    # =====================================================
    # تنظیمات Supabase (دیتابیس)
    # =====================================================
    SUPABASE_URL: str = Field(..., env="SUPABASE_URL")
    SUPABASE_ANON_KEY: str = Field(..., env="SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., env="SUPABASE_SERVICE_ROLE_KEY")
    SUPABASE_DB_URL: str = Field(..., env="SUPABASE_DB_URL")

    # =====================================================
    # تنظیمات JWT
    # =====================================================
    JWT_SECRET_KEY: str = Field(default="change-this-secret-key", env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # =====================================================
    # تنظیمات تلگرام
    # =====================================================
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)

    # =====================================================
    # تنظیمات لایسنس
    # =====================================================
    LICENSE_ENCRYPTION_KEY: str = Field(default="change-this-encryption-key-32-bytes!!", env="LICENSE_ENCRYPTION_KEY")
    LICENSE_SIGNATURE_KEY: str = Field(default="change-this-signature-key", env="LICENSE_SIGNATURE_KEY")

    # =====================================================
    # تنظیمات تحلیل بازار
    # =====================================================
    SYMBOLS_SUPPORTED: List[str] = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]
    DEFAULT_SYMBOL: str = "XAUUSD"
    DEFAULT_TIMEFRAMES: List[str] = ["M15", "H1", "H4", "D1"]

    # امتیازدهی
    MIN_ENTRY_SCORE: float = 65.0
    EXCELLENT_SCORE: float = 85.0
    GOOD_SCORE: float = 75.0
    MODERATE_SCORE: float = 65.0

    # وزن‌های امتیازدهی
    SMC_WEIGHT: float = 0.30
    PRICE_ACTION_WEIGHT: float = 0.25
    LIQUIDITY_WEIGHT: float = 0.15
    MTF_WEIGHT: float = 0.10
    SESSION_WEIGHT: float = 0.10
    VOLATILITY_WEIGHT: float = 0.10

    # =====================================================
    # تنظیمات ریسک
    # =====================================================
    MAX_RISK_PER_TRADE: float = 10.0  # درصد
    MAX_DAILY_RISK: float = 20.0  # درصد
    MAX_DAILY_TRADES: int = 50
    MAX_DRAWDOWN: float = 30.0  # درصد

    # =====================================================
    # تنظیمات سشن‌های معاملاتی
    # =====================================================
    KILLZONE_LONDON_START: str = "08:00"
    KILLZONE_LONDON_END: str = "11:00"
    KILLZONE_NEWYORK_START: str = "13:30"
    KILLZONE_NEWYORK_END: str = "16:00"
    KILLZONE_TOKYO_START: str = "00:30"
    KILLZONE_TOKYO_END: str = "02:00"

    # =====================================================
    # تنظیمات لاگ
    # =====================================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[str] = None

    # =====================================================
    # تنظیمات Redis (اختیاری)
    # =====================================================
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")

    # =====================================================
    # تنظیمات CORS
    # =====================================================
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    دریافت تنظیمات (کش شده)

    این تابع از lru_cache استفاده می‌کند تا تنظیمات فقط
    یک بار خوانده شوند و در حافظه ذخیره شوند.

    Returns:
        Settings: شیء تنظیمات
    """
    return Settings()


# نمونه گلوبال از تنظیمات
settings = get_settings()
