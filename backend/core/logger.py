"""
سیستم لاگ مرکزی

این ماژول سیستم لاگ یکپارچه را ارائه می‌دهد.
تمام لاگ‌ها با فرمت استاندارد و سطح‌بندی مناسب ثبت می‌شوند.
"""

import logging
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path
from .config import settings


class PersianFormatter(logging.Formatter):
    """
    فرمت‌کننده فارسی برای لاگ‌ها

    این کلاس پیام‌های لاگ را به فرمت خوانا تبدیل می‌کند.
    """

    # نام فارسی سطوح لاگ
    LEVEL_NAMES = {
        "DEBUG": "دیباگ",
        "INFO": "اطلاعات",
        "WARNING": "هشدار",
        "ERROR": "خطا",
        "CRITICAL": "بحرانی"
    }

    def format(self, record):
        # تبدیل سطح به فارسی
        level_fa = self.LEVEL_NAMES.get(record.levelname, record.levelname)

        # فرمت زمان
        record.asctime_fa = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        # فرمت اصلی
        formatted = f"[{record.asctime_fa}] [{level_fa}] [{record.name}] {record.getMessage()}"

        # اضافه کردن اطلاعات例外 در صورت وجود
        if record.exc_info:
            formatted += f"\n{self.formatException(record.exc_info)}"

        return formatted


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    راه‌اندازی لاگر

    Args:
        name: نام لاگر
        level: سطح لاگ (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: مسیر فایل لاگ (اختیاری)

    Returns:
        logging.Logger: شیء لاگر پیکربندی شده
    """
    # ایجاد لاگر
    logger = logging.getLogger(name)

    # تنظیم سطح
    log_level = level or settings.LOG_LEVEL
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # جلوگیری از تکرار هندلرها
    if logger.handlers:
        return logger

    # ایجاد فرمت‌کننده
    formatter = PersianFormatter()

    # هندلر کنسول
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # هندلر فایل (در صورت درخواست)
    if log_file:
        file_path = Path(log_file)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            log_file,
            encoding="utf-8",
            mode="a"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


class LogContext:
    """
    کانتکست لاگ برای ردیابی عملیات

    این کلاس امکان افزودن متادیتا به لاگ‌ها را فراهم می‌کند.
    """

    def __init__(self, logger: logging.Logger, **context):
        """
        مقداردهی اولیه

        Args:
            logger: لاگر اصلی
            **context: متادیتای اضافی
        """
        self.logger = logger
        self.context = context

    def _add_context(self, msg: str) -> str:
        """افزودن کانتکست به پیام"""
        if self.context:
            ctx_str = " | ".join(f"{k}={v}" for k, v in self.context.items())
            return f"[{ctx_str}] {msg}"
        return msg

    def debug(self, msg: str):
        """ثبت پیام دیباگ"""
        self.logger.debug(self._add_context(msg))

    def info(self, msg: str):
        """ثبت پیام اطلاعاتی"""
        self.logger.info(self._add_context(msg))

    def warning(self, msg: str):
        """ثبت هشدار"""
        self.logger.warning(self._add_context(msg))

    def error(self, msg: str):
        """ثبت خطا"""
        self.logger.error(self._add_context(msg))

    def critical(self, msg: str):
        """ثبت خطای بحرانی"""
        self.logger.critical(self._add_context(msg))


# لاگر پیش‌فرض
default_logger = setup_logger("mt5_trading")


def get_logger(name: str) -> logging.Logger:
    """
    دریافت لاگر با نام مشخص

    Args:
        name: نام ماژول یا کامپوننت

    Returns:
        logging.Logger: لاگر پیکربندی شده
    """
    return setup_logger(name)
