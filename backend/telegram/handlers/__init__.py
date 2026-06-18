"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Telegram Handlers — ثبت مرکزی همه هندلرها

هندلرهای فعال (11 هندلر):
  01. start          ← /start، منوی اصلی
  02. control        ← start/stop/pause/resume ربات
  03. trades         ← close_all/buy/sell معاملات
  04. signals        ← مشاهده و اجرای سیگنال‌ها
  05. reports        ← گزارش‌های روزانه/هفتگی/ماهانه
  06. alerts         ← هشدارهای trade/session/system
  07. settings       ← تنظیمات ربات
  08. admin_users    ← مدیریت کاربران (ADMIN+)
  09. semi_auto      ← تأیید سیگنال‌های Semi-Auto
  10. intelligence   ← یادگیری ماشین (ML) — فاز ۴
  11. research       ← بک‌تست و ریپلی — فاز ۳
"""

import logging
from aiogram import Dispatcher

from .start import register_start_handlers
from .control import register_control_handlers
from .trades import register_trade_handlers
from .signals import register_signal_handlers
from .reports import register_report_handlers
from .alerts import register_alert_handlers
from .settings import register_settings_handlers
from .admin_users import register_admin_user_handlers
from .semi_auto import register_semi_auto_handlers
from .intelligence import register_intelligence_handlers

logger = logging.getLogger("telegram.handlers")


def setup_handlers(dp: Dispatcher) -> None:
    """
    ثبت تمام هندلرهای تلگرام در Dispatcher.
    ترتیب ثبت اهمیت دارد — هندلرهای اختصاصی‌تر اول ثبت می‌شوند.
    """
    register_start_handlers(dp)
    logger.info("✅ start handlers ثبت شدند")

    register_control_handlers(dp)
    logger.info("✅ control handlers ثبت شدند")

    register_trade_handlers(dp)
    logger.info("✅ trade handlers ثبت شدند")

    register_signal_handlers(dp)
    logger.info("✅ signal handlers ثبت شدند")

    register_report_handlers(dp)
    logger.info("✅ report handlers ثبت شدند")

    register_alert_handlers(dp)
    logger.info("✅ alert handlers ثبت شدند")

    register_settings_handlers(dp)
    logger.info("✅ settings handlers ثبت شدند")

    register_admin_user_handlers(dp)
    logger.info("✅ admin_users handlers ثبت شدند")

    register_semi_auto_handlers(dp)
    logger.info("✅ semi_auto handlers ثبت شدند")

    # ─── فاز ۴: ML Learning System ───────────────────────────
    register_intelligence_handlers(dp)
    logger.info("✅ intelligence handlers ثبت شدند (فاز ۴)")

    logger.info("🚀 Galaxy Vast — همه 11 هندلر با موفقیت ثبت شدند")
