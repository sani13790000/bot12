"""
===============================================================================
Galaxy Vast AI Trading Platform
ثبت همه هندلرهای تلگرام

این فایل تمام هندلرها را به dispatcher اصلی وصل می‌کند.
ترتیب ثبت مهم است — هندلرهای عمومی‌تر بعد از خاص‌تر باشند.

نویسنده: Galaxy Vast Team
نسخه: 2.1.0 — فاز ۲: Semi-Auto handler اضافه شد
"""

import logging
from aiogram import Dispatcher

from .start import register_start_handlers
from .control import register_control_handlers
from .trades import register_trade_handlers
from .signals import register_signal_handlers
from .settings import register_settings_handlers
from .reports import register_report_handlers
from .alerts import register_alert_handlers
from .admin_users import register_admin_user_handlers
from .semi_auto import register_semi_auto_handlers

logger = logging.getLogger("telegram.handlers")


def setup_handlers(dp: Dispatcher) -> None:
    """
    ثبت تمام هندلرهای تلگرام در dispatcher

    ترتیب ثبت:
    ۱. start — پیام خوشامدگویی و منوی اصلی
    ۲. semi_auto — تأیید/رد سیگنال (callback های inline keyboard)
    ۳. control — کنترل ربات (start/stop/pause/resume)
    ۴. trades — مدیریت معاملات (close_all/buy/sell)
    ۵. signals — مشاهده و اجرای سیگنال‌ها
    ۶. reports — گزارش‌های روزانه/هفتگی/ماهانه
    ۷. alerts — هشدارهای خودکار
    ۸. settings — تنظیمات ربات
    ۹. admin_users — مدیریت کاربران (فقط ADMIN+)

    ورودی:
        dp: Dispatcher اصلی aiogram
    """
    register_start_handlers(dp)
    logger.debug("✅ start handlers ثبت شدند")

    register_semi_auto_handlers(dp)
    logger.debug("✅ semi_auto handlers ثبت شدند")

    register_control_handlers(dp)
    logger.debug("✅ control handlers ثبت شدند")

    register_trade_handlers(dp)
    logger.debug("✅ trade handlers ثبت شدند")

    register_signal_handlers(dp)
    logger.debug("✅ signal handlers ثبت شدند")

    register_report_handlers(dp)
    logger.debug("✅ report handlers ثبت شدند")

    register_alert_handlers(dp)
    logger.debug("✅ alert handlers ثبت شدند")

    register_settings_handlers(dp)
    logger.debug("✅ settings handlers ثبت شدند")

    register_admin_user_handlers(dp)
    logger.debug("✅ admin_users handlers ثبت شدند")

    logger.info("🌌 Galaxy Vast — تمام ۹ هندلر با موفقیت ثبت شدند")
