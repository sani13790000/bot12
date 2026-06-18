"""
تنظیمات مرکزی سیستم — Galaxy Vast AI Trading Platform

این فایل تمام تنظیمات قابل پیکربندی را مدیریت می‌کند.
تنظیمات از متغیرهای محیطی (environment variables) خوانده می‌شوند.
هیچ مقدار حساسی نباید در کد hardcode شود.

نویسنده: Galaxy Vast Team
نسخه: 2.1.0 — فاز ۲: Portfolio Risk + Daily Limits + Semi-Auto
"""

import os
from typing import List, Optional
from pydantic import BaseSettings, Field
from functools import lru_cache


class Settings(BaseSettings):
    """
    تنظیمات اصلی سیستم Galaxy Vast

    تمام تنظیمات از فایل .env یا متغیرهای محیطی خوانده می‌شوند.
    """

    # =====================================================
    # برند و هویت سیستم
    # =====================================================
    APP_NAME: str = "Galaxy Vast AI Trading Platform"
    APP_VERSION: str = "2.1.0"
    APP_BRAND: str = "Galaxy Vast"
    APP_DESCRIPTION: str = "سیستم هوشمند معامله‌گری نهادی — Galaxy Vast"
    APP_SUPPORT_USERNAME: str = "GalaxyVast_Support"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # =====================================================
    # تنظیمات API Gateway
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
    JWT_SECRET_KEY: str = Field(..., env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # =====================================================
    # تنظیمات تلگرام
    # =====================================================
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_ADMIN_IDS: List[int] = Field(default_factory=list)
    TELEGRAM_BOT_NAME: str = "Galaxy Vast Bot"

    # =====================================================
    # تنظیمات لایسنس
    # =====================================================
    LICENSE_ENCRYPTION_KEY: str = Field(..., env="LICENSE_ENCRYPTION_KEY")
    LICENSE_SIGNATURE_KEY: str = Field(..., env="LICENSE_SIGNATURE_KEY")

    # =====================================================
    # تنظیمات تحلیل بازار
    # =====================================================
    SYMBOLS_SUPPORTED: List[str] = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"]
    DEFAULT_SYMBOL: str = "XAUUSD"
    DEFAULT_TIMEFRAMES: List[str] = ["M15", "H1", "H4", "D1"]

    # آستانه‌های امتیازدهی
    MIN_ENTRY_SCORE: float = 65.0
    EXCELLENT_SCORE: float = 85.0
    GOOD_SCORE: float = 75.0
    MODERATE_SCORE: float = 65.0

    # وزن‌های امتیازدهی تحلیل
    SMC_WEIGHT: float = 0.40
    PRICE_ACTION_WEIGHT: float = 0.25
    HTF_WEIGHT: float = 0.20
    SESSION_WEIGHT: float = 0.10
    LTF_WEIGHT: float = 0.05

    # =====================================================
    # تنظیمات مدیریت ریسک — معامله تکی
    # =====================================================
    MAX_RISK_PER_TRADE: float = 2.0         # درصد از موجودی
    MAX_SPREAD_POINTS: int = 30             # حداکثر اسپرد مجاز

    # =====================================================
    # تنظیمات ریسک پرتفولیو — فاز ۲ (جدید)
    # =====================================================
    MAX_PORTFOLIO_RISK_PERCENT: float = 5.0     # حداکثر ریسک کل همه معاملات باز
    MAX_SINGLE_CURRENCY_EXPOSURE: float = 3.0   # حداکثر exposure یک ارز
    CORRELATION_RISK_MULTIPLIER: float = 0.3    # ضریب جریمه همبستگی

    # =====================================================
    # محدودیت‌های زمانی — فاز ۲ (جدید)
    # =====================================================
    MAX_DAILY_TRADES: int = 5               # حداکثر معاملات در روز
    MAX_DAILY_LOSS_PERCENT: float = 3.0     # حداکثر ضرر روزانه (درصد موجودی)
    MAX_WEEKLY_LOSS_PERCENT: float = 7.0    # حداکثر ضرر هفتگی (درصد موجودی)
    MAX_MONTHLY_DRAWDOWN_PERCENT: float = 15.0  # حداکثر drawdown ماهانه

    # =====================================================
    # تنظیمات Semi-Auto Mode — فاز ۲ (جدید)
    # =====================================================
    TRADING_MODE: str = "FULL_AUTO"         # SIGNAL_ONLY | SEMI_AUTO | FULL_AUTO
    SEMI_AUTO_CONFIRMATION_TIMEOUT_SECONDS: int = 120  # ۲ دقیقه برای تأیید

    # =====================================================
    # تنظیمات سشن‌های Kill Zone
    # =====================================================
    KILLZONE_LONDON_START: str = "08:00"
    KILLZONE_LONDON_END: str = "10:00"
    KILLZONE_NEWYORK_START: str = "13:00"
    KILLZONE_NEWYORK_END: str = "15:00"
    KILLZONE_TOKYO_START: str = "00:00"
    KILLZONE_TOKYO_END: str = "04:00"
    KILLZONE_LONDON_CLOSE_START: str = "15:00"
    KILLZONE_LONDON_CLOSE_END: str = "16:00"

    # =====================================================
    # تنظیمات لاگ
    # =====================================================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_FILE: Optional[str] = "logs/galaxy_vast.log"

    # =====================================================
    # تنظیمات Redis (اختیاری)
    # =====================================================
    REDIS_URL: Optional[str] = Field(default=None, env="REDIS_URL")

    # =====================================================
    # تنظیمات CORS
    # =====================================================
    CORS_ORIGINS: List[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "https://galaxyvast.com",
        ]
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """
    دریافت تنظیمات (کش شده)

    این تابع از lru_cache استفاده می‌کند تا تنظیمات فقط
    یک بار خوانده شود و در حافظه ذخیره شود.

    Returns:
        Settings: شیء تنظیمات
    """
    return Settings()


# نمونه گلوبال از تنظیمات
settings = get_settings()
