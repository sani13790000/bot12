"""
کیبوردهای ربات تلگرام

نویسنده: MT5 Trading Team
"""

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """
    کیبورد اصلی منو
    """
    builder = ReplyKeyboardBuilder()
    builder.add(KeyboardButton(text="📊 تحلیل بازار"))
    builder.add(KeyboardButton(text="📈 معاملات من"))
    builder.add(KeyboardButton(text="🔔 سیگنال‌ها"))
    builder.add(KeyboardButton(text="⚙️ تنظیمات"))
    builder.add(KeyboardButton(text="📋 گزارش‌ها"))
    builder.add(KeyboardButton(text="❓ راهنما"))
    builder.adjust(2, 2, 2)
    return builder.as_markup(resize_keyboard=True)


def get_analysis_keyboard() -> InlineKeyboardMarkup:
    """
    کیبورد تحلیل
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="EURUSD", callback_data="analyze_EURUSD"))
    builder.add(InlineKeyboardButton(text="GBPUSD", callback_data="analyze_GBPUSD"))
    builder.add(InlineKeyboardButton(text="USDJPY", callback_data="analyze_USDJPY"))
    builder.add(InlineKeyboardButton(text="XAUUSD", callback_data="analyze_XAUUSD"))
    builder.add(InlineKeyboardButton(text="BTCUSD", callback_data="analyze_BTCUSD"))
    builder.add(InlineKeyboardButton(text="🔍 نماد سفارشی", callback_data="custom_symbol"))
    builder.adjust(3, 3)
    return builder.as_markup()


def get_timeframe_keyboard() -> InlineKeyboardMarkup:
    """
    کیبورد انتخاب تایم‌فریم
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="M1", callback_data="tf_M1"))
    builder.add(InlineKeyboardButton(text="M5", callback_data="tf_M5"))
    builder.add(InlineKeyboardButton(text="M15", callback_data="tf_M15"))
    builder.add(InlineKeyboardButton(text="M30", callback_data="tf_M30"))
    builder.add(InlineKeyboardButton(text="H1", callback_data="tf_H1"))
    builder.add(InlineKeyboardButton(text="H4", callback_data="tf_H4"))
    builder.add(InlineKeyboardButton(text="D1", callback_data="tf_D1"))
    builder.add(InlineKeyboardButton(text="W1", callback_data="tf_W1"))
    builder.adjust(4, 4)
    return builder.as_markup()


def get_settings_keyboard() -> InlineKeyboardMarkup:
    """
    کیبورد تنظیمات
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🎯 حد ضرر/سود", callback_data="settings_sltp"))
    builder.add(InlineKeyboardButton(text="💰 مدیریت سرمایه", callback_data="settings_risk"))
    builder.add(InlineKeyboardButton(text="📊 نماد پیش‌فرض", callback_data="settings_symbol"))
    builder.add(InlineKeyboardButton(text="🔔 اعلان‌ها", callback_data="settings_notifications"))
    builder.add(InlineKeyboardButton(text="⏰ تایم‌فریم پیش‌فرض", callback_data="settings_timeframe"))
    builder.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    builder.adjust(2, 2, 2)
    return builder.as_markup()


def get_trades_keyboard() -> InlineKeyboardMarkup:
    """
    کیبورد معاملات
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📋 معاملات باز", callback_data="trades_open"))
    builder.add(InlineKeyboardButton(text="📜 تاریخچه", callback_data="trades_history"))
    builder.add(InlineKeyboardButton(text="❌ بستن همه", callback_data="trades_close_all"))
    builder.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    builder.adjust(2, 2)
    return builder.as_markup()


def get_signals_keyboard() -> InlineKeyboardMarkup:
    """
    کیبورد سیگنال‌ها
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="🔔 سیگنال‌های فعال", callback_data="signals_active"))
    builder.add(InlineKeyboardButton(text="📜 تاریخچه سیگنال‌ها", callback_data="signals_history"))
    builder.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    builder.adjust(2, 1)
    return builder.as_markup()


def get_reports_keyboard() -> InlineKeyboardMarkup:
    """
    کیبورد گزارش‌ها
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📅 گزارش روزانه", callback_data="report_daily"))
    builder.add(InlineKeyboardButton(text="📆 گزارش هفتگی", callback_data="report_weekly"))
    builder.add(InlineKeyboardButton(text="🗓 گزارش ماهانه", callback_data="report_monthly"))
    builder.add(InlineKeyboardButton(text="📊 عملکرد کلی", callback_data="report_performance"))
    builder.add(InlineKeyboardButton(text="🔙 بازگشت", callback_data="back_main"))
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def get_confirm_keyboard(action: str) -> InlineKeyboardMarkup:
    """
    کیبورد تأیید
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ بله", callback_data=f"confirm_{action}"))
    builder.add(InlineKeyboardButton(text="❌ خیر", callback_data=f"cancel_{action}"))
    return builder.as_markup()


def get_signal_action_keyboard(signal_id: str) -> InlineKeyboardMarkup:
    """
    کیبورد عملیات روی سیگنال
    """
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✅ اجرا",
        callback_data=f"signal_execute_{signal_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="⏭ رد کردن",
        callback_data=f"signal_skip_{signal_id}"
    ))
    builder.add(InlineKeyboardButton(
        text="🔔 یادآوری بعدا",
        callback_data=f"signal_remind_{signal_id}"
    ))
    builder.adjust(3)
    return builder.as_markup()


def get_pagination_keyboard(
    current_page: int,
    total_pages: int,
    callback_prefix: str
) -> InlineKeyboardMarkup:
    """
    کیبورد صفحه‌بندی
    """
    builder = InlineKeyboardBuilder()

    if current_page > 1:
        builder.add(InlineKeyboardButton(
            text="◀️ قبلی",
            callback_data=f"{callback_prefix}_{current_page - 1}"
        ))

    builder.add(InlineKeyboardButton(
        text=f"{current_page}/{total_pages}",
        callback_data="page_info"
    ))

    if current_page < total_pages:
        builder.add(InlineKeyboardButton(
            text="بعدی ▶️",
            callback_data=f"{callback_prefix}_{current_page + 1}"
        ))

    builder.add(InlineKeyboardButton(
        text="🔙 بازگشت",
        callback_data="back_main"
    ))

    builder.adjust(3, 1)
    return builder.as_markup()
