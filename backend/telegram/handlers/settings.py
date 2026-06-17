"""
هندلرهای تنظیمات

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import httpx

from ..keyboards import get_settings_keyboard, get_main_keyboard
from ....core.logger import get_logger

logger = get_logger("telegram.handlers.settings")


class SettingsState(StatesGroup):
    """وضعیت‌های تنظیمات"""
    waiting_value = State()


def register_settings_handlers(dp: Dispatcher):
    """ثبت هندلرهای تنظیمات"""

    @dp.message(F.text == "⚙️ تنظیمات")
    async def menu_settings(message: types.Message):
        """نمایش منوی تنظیمات"""
        await message.answer(
            "⚙️ <b>تنظیمات</b>\n\n"
            "گزینه مورد نظر را انتخاب کنید:",
            reply_markup=get_settings_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data == "settings_sltp")
    async def settings_sltp(callback: types.CallbackQuery, state: FSMContext):
        """تنظیم حد ضرر/سود"""
        await callback.message.edit_text(
            "🎯 <b>تنظیم حد ضرر/سود</b>\n\n"
            "مقادیر فعلی را مشاهده کنید:\n\n"
            "حد ضرر پیش‌فرض: 50 پوینت\n"
            "حد سود پیش‌فرض: 100 پوینت\n\n"
            "برای تغییر، مقدار جدید را وارد کنید.\n"
            "مثال: <code>sl:50 tp:100</code>",
            parse_mode="HTML"
        )
        await state.set_state(SettingsState.waiting_value)
        await state.update_data(setting_type="sltp")
        await callback.answer()

    @dp.callback_query(F.data == "settings_risk")
    async def settings_risk(callback: types.CallbackQuery, state: FSMContext):
        """تنظیم مدیریت سرمایه"""
        await callback.message.edit_text(
            "💰 <b>مدیریت سرمایه</b>\n\n"
            "مقادیر فعلی:\n\n"
            "ریسک هر معامله: 1%\n"
            "حداکثر معاملات روزانه: 5\n"
            "حداکثر معاملات همزمان: 3\n\n"
            "برای تغییر، مقدار جدید را وارد کنید.\n"
            "مثال: <code>risk:2 max:3</code>",
            parse_mode="HTML"
        )
        await state.set_state(SettingsState.waiting_value)
        await state.update_data(setting_type="risk")
        await callback.answer()

    @dp.callback_query(F.data == "settings_symbol")
    async def settings_symbol(callback: types.CallbackQuery, state: FSMContext):
        """تنظیم نماد پیش‌فرض"""
        await callback.message.edit_text(
            "📊 <b>نماد پیش‌فرض</b>\n\n"
            "نماد پیش‌فرض فعلی: EURUSD\n\n"
            "نماد جدید را وارد کنید:\n"
            "مثال: <code>GBPUSD</code> یا <code>XAUUSD</code>",
            parse_mode="HTML"
        )
        await state.set_state(SettingsState.waiting_value)
        await state.update_data(setting_type="symbol")
        await callback.answer()

    @dp.callback_query(F.data == "settings_notifications")
    async def settings_notifications(callback: types.CallbackQuery):
        """تنظیم اعلان‌ها"""
        await callback.message.edit_text(
            "🔔 <b>تنظیم اعلان‌ها</b>\n\n"
            "وضعیت فعلی:\n\n"
            "✅ اعلان سیگنال‌ها: فعال\n"
            "✅ اعلان معاملات: فعال\n"
            "❌ اعلان اخبار: غیرفعال\n"
            "✅ گزارش روزانه: فعال\n\n"
            "برای تغییر هر گزینه، روی آن کلیک کنید.",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="🔔 اعلان سیگنال",
                            callback_data="toggle_signal_notif"
                        ),
                        types.InlineKeyboardButton(
                            text="📈 اعلان معاملات",
                            callback_data="toggle_trade_notif"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="📰 اعلان اخبار",
                            callback_data="toggle_news_notif"
                        ),
                        types.InlineKeyboardButton(
                            text="📋 گزارش روزانه",
                            callback_data="toggle_report_notif"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="🔙 بازگشت",
                            callback_data="back_settings"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "settings_timeframe")
    async def settings_timeframe(callback: types.CallbackQuery, state: FSMContext):
        """تنظیم تایم‌فریم پیش‌فرض"""
        await callback.message.edit_text(
            "⏰ <b>تایم‌فریم پیش‌فرض</b>\n\n"
            "تایم‌فریم فعلی: H1\n\n"
            "تایم‌فریم جدید را انتخاب کنید:",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        types.InlineKeyboardButton(text="M5", callback_data="set_tf_M5"),
                        types.InlineKeyboardButton(text="M15", callback_data="set_tf_M15"),
                        types.InlineKeyboardButton(text="M30", callback_data="set_tf_M30")
                    ],
                    [
                        types.InlineKeyboardButton(text="H1", callback_data="set_tf_H1"),
                        types.InlineKeyboardButton(text="H4", callback_data="set_tf_H4"),
                        types.InlineKeyboardButton(text="D1", callback_data="set_tf_D1")
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="🔙 بازگشت",
                            callback_data="back_settings"
                        )
                    ]
                ]
            ),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("set_tf_"))
    async def set_timeframe(callback: types.CallbackQuery):
        """ثبت تایم‌فریم"""
        tf = callback.data.split("_")[2]
        await callback.message.edit_text(
            f"✅ <b>تایم‌فریم پیش‌فرض</b>\n\n"
            f"تایم‌فریم جدید: <b>{tf}</b>",
            parse_mode="HTML"
        )
        await callback.answer("تایم‌فریم ذخیره شد")

    @dp.callback_query(F.data == "back_settings")
    async def back_settings(callback: types.CallbackQuery):
        """بازگشت به منوی تنظیمات"""
        await callback.message.edit_text(
            "⚙️ <b>تنظیمات</b>\n\n"
            "گزینه مورد نظر را انتخاب کنید:",
            reply_markup=get_settings_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.message(SettingsState.waiting_value)
    async def process_setting_value(message: types.Message, state: FSMContext):
        """پردازش مقدار تنظیمات"""
        data = await state.get_data()
        setting_type = data.get("setting_type")
        value = message.text.strip()

        # در اینجا باید مقدار را در دیتابیس ذخیره کنیم
        await message.answer(
            f"✅ <b>تنظیمات ذخیره شد</b>\n\n"
            f"مقدار جدید: <code>{value}</code>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )

        await state.clear()
