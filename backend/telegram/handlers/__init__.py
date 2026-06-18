"""
هندلرهای ربات تلگرام

این فایل تمام هندلرهای ربات تلگرام را ثبت می‌کند.
هر هندلر مستقل است و می‌تواند فعال/غیرفعال شود.

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher

from .start import register_start_handlers
from .analysis import register_analysis_handlers
from .trades import register_trade_handlers
from .signals import register_signal_handlers
from .settings import register_settings_handlers
from .reports import register_report_handlers
from .control import register_control_handlers
from .alerts import register_alert_handlers
from .admin_users import register_admin_user_handlers

from ....core.logger import get_logger

logger = get_logger("telegram.handlers")


def setup_handlers(dp: Dispatcher) -> None:
    """
    ثبت تمام هندلرهای ربات تلگرام

    ترتیب ثبت مهم است:
    ابتدا هندلرهای اصلی، سپس admin، سپس fallback
    """

    # --- هندلر اصلی شروع ---
    register_start_handlers(dp)
    logger.debug("هندلر start ثبت شد")

    # --- هندلر کنترل ربات (start/stop/pause/resume) ---
    register_control_handlers(dp)
    logger.debug("هندلر control ثبت شد")

    # --- هندلر تحلیل بازار ---
    register_analysis_handlers(dp)
    logger.debug("هندلر analysis ثبت شد")

    # --- هندلر معاملات ---
    register_trade_handlers(dp)
    logger.debug("هندلر trades ثبت شد")

    # --- هندلر سیگنال‌ها ---
    register_signal_handlers(dp)
    logger.debug("هندلر signals ثبت شد")

    # --- هندلر تنظیمات ---
    register_settings_handlers(dp)
    logger.debug("هندلر settings ثبت شد")

    # --- هندلر گزارش‌ها ---
    register_report_handlers(dp)
    logger.debug("هندلر reports ثبت شد")

    # --- هندلر هشدارها (alert callbacks) ---
    register_alert_handlers(dp)
    logger.debug("هندلر alerts ثبت شد")

    # --- هندلر مدیریت کاربران (فقط ADMIN+) ---
    register_admin_user_handlers(dp)
    logger.debug("هندلر admin_users ثبت شد")

    logger.info("تمام هندلرهای تلگرام با موفقیت ثبت شدند — ۹ هندلر فعال")
