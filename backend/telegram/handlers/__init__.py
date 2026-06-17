"""
هندلرهای ربات تلگرام

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher
from .start import register_start_handlers
from .analysis import register_analysis_handlers
from .trades import register_trade_handlers
from .signals import register_signal_handlers
from .settings import register_settings_handlers
from .reports import register_report_handlers


def setup_handlers(dp: Dispatcher):
    """
    ثبت همه هندلرها
    """
    register_start_handlers(dp)
    register_analysis_handlers(dp)
    register_trade_handlers(dp)
    register_signal_handlers(dp)
    register_settings_handlers(dp)
    register_report_handlers(dp)
