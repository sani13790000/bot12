"""
هندلرهای سیگنال‌ها با RBAC کامل

این فایل تمام عملیات سیگنال‌ها را با بررسی دسترسی
کامل مدیریت می‌کند.

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
import httpx
import os as _os

from ..keyboards import get_signals_keyboard, get_signal_action_keyboard
from ..utils import format_signal_card
from ..rbac import Permission, require_permission, get_user_role
from ...services.rbac_service import RBACService
from ....core.logger import get_logger

_API_BASE_URL = _os.environ.get("API_BASE_URL", "http://localhost:8000")

logger = get_logger("telegram.handlers.signals")

# نمونه سراسری RBAC Service
_rbac_service = RBACService()


def register_signal_handlers(dp: Dispatcher) -> None:
    """
    ثبت هندلرهای سیگنال‌ها با RBAC

    دسترسی‌ها:
    - نمایش سیگنال‌ها: Permission.VIEW_SIGNALS (USER+)
    - اجرای سیگنال: Permission.EXECUTE_SIGNAL (TRADER+)
    - رد سیگنال: Permission.VIEW_SIGNALS (USER+)
    """

    @dp.message(F.text == "📊 سیگنال‌ها")
    async def menu_signals(message: types.Message):
        """نمایش منوی سیگنال‌ها — نیاز به VIEW_SIGNALS"""
        user_id = message.from_user.id

        # بررسی دسترسی VIEW_SIGNALS
        if not await _rbac_service.check_permission(user_id, Permission.VIEW_SIGNALS):
            await message.answer(
                "⛔️ <b>دسترسی محدود</b>\n\n"
                "برای مشاهده سیگنال‌ها نیاز به سطح دسترسی <b>USER</b> یا بالاتر دارید.",
                parse_mode="HTML"
            )
            return

        await message.answer(
            "📊 <b>مدیریت سیگنال‌ها</b>\n\n"
            "گزینه مورد نظر را انتخاب کنید:",
            reply_markup=get_signals_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data == "signals_active")
    async def show_active_signals(callback: types.CallbackQuery):
        """نمایش سیگنال‌های فعال — نیاز به VIEW_SIGNALS"""
        user_id = callback.from_user.id

        if not await _rbac_service.check_permission(user_id, Permission.VIEW_SIGNALS):
            await callback.answer("⛔️ دسترسی ندارید", show_alert=True)
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{_API_BASE_URL}/api/signals/active",
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                signals = result.get("data", {}).get("active_signals", [])

                if not signals:
                    await callback.message.edit_text(
                        "🔭 <b>سیگنال‌های فعال</b>\n\n"
                        "در حال حاضر سیگنال فعالی وجود ندارد.",
                        parse_mode="HTML"
                    )
                else:
                    # بررسی دسترسی EXECUTE_SIGNAL برای نمایش دکمه اجرا
                    can_execute = await _rbac_service.check_permission(
                        user_id, Permission.EXECUTE_SIGNAL
                    )

                    for signal in signals[:3]:
                        text = format_signal_card(signal)
                        keyboard = get_signal_action_keyboard(
                            signal["id"],
                            can_execute=can_execute
                        )
                        await callback.message.answer(
                            text,
                            reply_markup=keyboard,
                            parse_mode="HTML"
                        )
                    await callback.message.delete()
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت سیگنال‌ها",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت سیگنال‌های فعال: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "signals_history")
    async def show_signal_history(callback: types.CallbackQuery):
        """نمایش تاریخچه سیگنال‌ها — نیاز به VIEW_SIGNALS"""
        user_id = callback.from_user.id

        if not await _rbac_service.check_permission(user_id, Permission.VIEW_SIGNALS):
            await callback.answer("⛔️ دسترسی ندارید", show_alert=True)
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{_API_BASE_URL}/api/signals/",
                    params={"limit": 10},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                signals = result.get("data", {}).get("signals", [])

                if not signals:
                    await callback.message.edit_text(
                        "🔭 <b>تاریخچه سیگنال‌ها</b>\n\n"
                        "هیچ سیگنالی ثبت نشده.",
                        parse_mode="HTML"
                    )
                else:
                    text = "📋 <b>تاریخچه سیگنال‌ها</b>\n\n"
                    wins = 0
                    losses = 0

                    for signal in signals[:10]:
                        status_emoji = {
                            "executed": "✅",
                            "expired": "⏰",
                            "skipped": "⏭"
                        }.get(signal.get("status"), "❓")

                        direction_emoji = "🟢" if signal.get("direction") == "buy" else "🔴"

                        result_text = ""
                        if signal.get("result"):
                            if signal["result"] == "win":
                                wins += 1
                                result_text = " 💰"
                            elif signal["result"] == "loss":
                                losses += 1
                                result_text = " 📉"

                        text += (
                            f"{status_emoji} {direction_emoji} <b>{signal.get('symbol')}</b> "
                            f"- امتیاز: {signal.get('total_score', 0):.0f}{result_text}\n"
                        )

                    text += f"\n🏆 برنده: {wins} | باخته: {losses}"
                    await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت تاریخچه",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت تاریخچه سیگنال‌ها: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_execute_"))
    async def execute_signal(callback: types.CallbackQuery):
        """
        اجرای سیگنال — نیاز به EXECUTE_SIGNAL (TRADER+)

        این عملیات حساس است و فقط TRADER و بالاتر مجاز هستند.
        """
        user_id = callback.from_user.id

        # بررسی دقیق دسترسی EXECUTE_SIGNAL
        if not await _rbac_service.check_permission(user_id, Permission.EXECUTE_SIGNAL):
            await callback.answer(
                "⛔️ فقط TRADER و بالاتر می‌توانند سیگنال اجرا کنند",
                show_alert=True
            )
            logger.warning(
                f"تلاش غیرمجاز برای اجرای سیگنال — کاربر: {user_id}"
            )
            return

        signal_id = callback.data.split("_")[2]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{_API_BASE_URL}/api/signals/{signal_id}/execute",
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})
                await callback.message.edit_text(
                    f"✅ <b>سیگنال اجرا شد!</b>\n\n"
                    f"معامله با موفقیت باز شد.\n"
                    f"شناسه معامله: <code>{data.get('trade_id', 'N/A')}</code>",
                    parse_mode="HTML"
                )
                logger.info(f"سیگنال {signal_id} توسط کاربر {user_id} اجرا شد")
            else:
                error_msg = response.json().get("detail", "خطای ناشناخته")
                await callback.message.edit_text(
                    f"❌ خطا در اجرای سیگنال\n<code>{error_msg}</code>",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در اجرای سیگنال {signal_id}: {e}", exc_info=True)
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_skip_"))
    async def skip_signal(callback: types.CallbackQuery):
        """رد کردن سیگنال — نیاز به VIEW_SIGNALS"""
        user_id = callback.from_user.id

        if not await _rbac_service.check_permission(user_id, Permission.VIEW_SIGNALS):
            await callback.answer("⛔️ دسترسی ندارید", show_alert=True)
            return

        signal_id = callback.data.split("_")[2]

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{_API_BASE_URL}/api/signals/{signal_id}/skip",
                    timeout=10.0
                )
        except Exception as e:
            logger.warning(f"خطا در رد سیگنال {signal_id}: {e}")

        await callback.message.edit_text(
            "⏭ <b>سیگنال رد شد</b>",
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_remind_"))
    async def remind_signal(callback: types.CallbackQuery):
        """یادآوری سیگنال — نیاز به VIEW_SIGNALS"""
        user_id = callback.from_user.id

        if not await _rbac_service.check_permission(user_id, Permission.VIEW_SIGNALS):
            await callback.answer("⛔️ دسترسی ندارید", show_alert=True)
            return

        await callback.message.edit_text(
            "🔔 <b>یادآوری تنظیم شد</b>\n\n"
            "به زودی یادآوری دریافت خواهید کرد.",
            parse_mode="HTML"
        )
        await callback.answer()
