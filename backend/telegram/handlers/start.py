"""
هندلر شروع و منوی اصلی

با پشتیبانی RBAC و Authorization.

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from ..keyboards import get_main_keyboard
from ..utils import format_welcome_message
from ..auth import (
    require_permission, require_role, rate_limit,
    Permission, UserRole
)
from ..rbac_service import rbac_service
from ....core.logger import get_logger
from ....services.audit_service import audit_service, AuditAction

logger = get_logger("telegram.handlers.start")


def register_start_handlers(dp: Dispatcher):
    """ثبت هندلرهای شروع"""

    @dp.message(CommandStart())
    @rate_limit("command")
    async def cmd_start(message: types.Message, state: FSMContext):
        """
        هندلر دستور /start

        کاربر جدید: ثبت‌نام خودکار
        کاربر موجود: نمایش منوی اصلی
        """
        await state.clear()

        user_id = message.from_user.id
        username = message.from_user.username or "کاربر"

        # بررسی یا ثبت کاربر
        user = await rbac_service.get_user_by_telegram_id(user_id)

        if not user:
            # ثبت کاربر جدید
            result = await rbac_service.register_telegram_user(
                telegram_user_id=user_id,
                telegram_username=username
            )

            if result.get("success"):
                # ثبت audit برای کاربر جدید
                await audit_service.log(
                    action=AuditAction.LOGIN,
                    user_id=result.get("user", {}).get("id"),
                    details={"new_user": True, "telegram_username": username}
                )
            else:
                logger.error(f"خطا در ثبت کاربر جدید: {result}")

            logger.info(f"کاربر جدید ثبت شد: {user_id} (@{username})")

        # نمایش پیام خوش‌آمدگویی
        await message.answer(
            format_welcome_message(username),
            reply_markup=get_main_keyboard(),
            parse_mode="HTML"
        )

    @dp.message(Command("help"))
    @rate_limit("command")
    async def cmd_help(message: types.Message):
        """
        هندلر دستور /help

        نمایش راهنما بر اساس نقش کاربر
        """
        user_id = message.from_user.id
        role = await rbac_service.get_user_role(user_id)

        # راهنما بر اساس نقش
        base_help = """
📖 <b>راهنمای استفاده از ربات</b>

<b>📊 تحلیل بازار:</b>
تحلیل SMC و Price Action نمادها

<b>📈 معاملات:</b>
مشاهده معاملات باز و بسته شده

<b>🔔 سیگنال‌ها:</b>
سیگنال‌های خرید و فروش با حد ضرر/سود

<b>📋 گزارش‌ها:</b>
گزارش روزانه، هفتگی و ماهانه

<b>دستورات پایه:</b>
/start - شروع
/help - راهنما
/status - وضعیت اکانت
/balance - موجودی
"""

        trader_commands = """
<b>📈 معاملات:</b>
/trades - لیست معاملات
/positions - معاملات باز
/close_all - بستن همه معاملات
/close_buy - بستن خریدها
/close_sell - بستن فروشها
"""

        admin_commands = """
<b>🔧 مدیریت:</b>
/start_bot - شروع ربات
/stop_bot - توقف ربات
/users - لیست کاربران
"""

        # اضافه کردن دستورات بر اساس نقش
        if role and role.value in ["trader", "admin", "super_admin"]:
            base_help += trader_commands

        if role and role.value in ["admin", "super_admin"]:
            base_help += admin_commands

        base_help += """
<b>⚠️ توجه:</b>
حداقل امتیاز ورود: 65 از 100
"""

        await message.answer(base_help, parse_mode="HTML")

    @dp.message(Command("status"))
    @rate_limit("command")
    async def cmd_status(message: types.Message):
        """
        هندلر دستور /status

        نمایش وضعیت اکانت کاربر
        """
        user_id = message.from_user.id
        user = await rbac_service.get_user_by_telegram_id(user_id)

        if not user:
            await message.answer(
                "⚠️ شما در سیستم ثبت نشده‌اید.\n\n"
                "لطفاً ابتدا در داشبورد ثبت‌نام کنید.",
                parse_mode="HTML"
            )
            return

        role = user.get("role", "user")
        status = user.get("status", "active")

        role_names = {
            "user": "کاربر عادی",
            "trader": "معامله‌گر",
            "admin": "مدیر",
            "super_admin": "مدیر کل"
        }

        status_text = f"""
📊 <b>وضعیت اکانت</b>

👤 <b>کاربر:</b> {message.from_user.username or "ناشناس"}
🆔 <b>Telegram ID:</b> {user_id}
📧 <b>ایمیل:</b> {user.get("email", "ثبت نشده")}
🏷️ <b>نقش:</b> {role_names.get(role, role)}
✅ <b>وضعیت:</b> {"فعال" if status == "active" else "غیرفعال"}
"""
        await message.answer(status_text, parse_mode="HTML")

    @dp.message(Command("balance"))
    @rate_limit("command")
    async def cmd_balance(message: types.Message):
        """
        هندلر دستور /balance

        نمایش اطلاعات حساب (نیازمند ثبت‌نام)
        """
        user_id = message.from_user.id
        user = await rbac_service.get_user_by_telegram_id(user_id)

        if not user:
            await message.answer(
                "⚠️ برای مشاهده موجودی باید ثبت‌نام کنید.",
                parse_mode="HTML"
            )
            return

        # در حالت واقعی باید از API دریافت شود
        balance_text = """
💰 <b>اطلاعات حساب</b>

💵 موجودی: $10,000.00
📊 اکوئیتی: $10,100.00
📈 سود/ضرر روز: $100.00
📉 مارجین استفاده: $500.00
🔐 مارجین آزاد: $9,500.00
"""
        await message.answer(balance_text, parse_mode="HTML")

    @dp.message(F.text == "❓ راهنما")
    async def menu_help(message: types.Message):
        """هندلر دکمه راهنما"""
        await cmd_help(message)

    @dp.callback_query(F.data == "back_main")
    async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
        """بازگشت به منوی اصلی"""
        await state.clear()
        await callback.message.edit_text(
            "🏠 <b>منوی اصلی</b>",
            parse_mode="HTML"
        )
        await callback.message.answer(
            "چه کاری می‌خواهید انجام کنید؟",
            reply_markup=get_main_keyboard()
        )
        await callback.answer()
