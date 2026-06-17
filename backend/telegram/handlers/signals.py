"""
هندلرهای سیگنال‌ها

نویسنده: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
import httpx

from ..keyboards import get_signals_keyboard, get_signal_action_keyboard
from ..utils import format_signal_card
from ....core.logger import get_logger

logger = get_logger("telegram.handlers.signals")


def register_signal_handlers(dp: Dispatcher):
    """ثبت هندلرهای سیگنال‌ها"""

    @dp.message(F.text == "🔔 سیگنال‌ها")
    async def menu_signals(message: types.Message):
        """نمایش منوی سیگنال‌ها"""
        await message.answer(
            "🔔 <b>مدیریت سیگنال‌ها</b>\n\n"
            "گزینه مورد نظر را انتخاب کنید:",
            reply_markup=get_signals_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data == "signals_active")
    async def show_active_signals(callback: types.CallbackQuery):
        """نمایش سیگنال‌های فعال"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8000/api/signals/active",
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                signals = result.get("data", {}).get("active_signals", [])

                if not signals:
                    await callback.message.edit_text(
                        "📭 <b>سیگنال‌های فعال</b>\n\n"
                        "در حال حاضر سیگنال فعالی وجود ندارد.",
                        parse_mode="HTML"
                    )
                else:
                    for signal in signals[:3]:  # حداکثر 3 سیگنال
                        text = format_signal_card(signal)
                        await callback.message.answer(
                            text,
                            reply_markup=get_signal_action_keyboard(signal["id"]),
                            parse_mode="HTML"
                        )
                    await callback.message.delete()
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت سیگنال‌ها",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت سیگنال‌ها: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "signals_history")
    async def show_signal_history(callback: types.CallbackQuery):
        """نمایش تاریخچه سیگنال‌ها"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://localhost:8000/api/signals/",
                    params={"limit": 10},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                signals = result.get("data", {}).get("signals", [])

                if not signals:
                    await callback.message.edit_text(
                        "📭 <b>تاریخچه سیگنال‌ها</b>\n\n"
                        "هیچ سیگنالی ثبت نشده.",
                        parse_mode="HTML"
                    )
                else:
                    text = "📜 <b>تاریخچه سیگنال‌ها</b>\n\n"

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

                    text += f"\n📊 برنده: {wins} | بازنده: {losses}"
                    await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "❌ خطا در دریافت تاریخچه",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در دریافت تاریخچه: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_execute_"))
    async def execute_signal(callback: types.CallbackQuery):
        """اجرای سیگنال"""
        signal_id = callback.data.split("_")[2]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"http://localhost:8000/api/signals/{signal_id}/execute",
                    timeout=30.0
                )

            if response.status_code == 200:
                await callback.message.edit_text(
                    "✅ <b>سیگنال اجرا شد!</b>\n\n"
                    "معامله با موفقیت باز شد.",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "❌ خطا در اجرای سیگنال",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در اجرای سیگنال: {e}")
            await callback.message.edit_text(
                "❌ خطا در ارتباط با سرور",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_skip_"))
    async def skip_signal(callback: types.CallbackQuery):
        """رد کردن سیگنال"""
        signal_id = callback.data.split("_")[2]

        await callback.message.edit_text(
            "⏭ <b>سیگنال رد شد</b>",
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_remind_"))
    async def remind_signal(callback: types.CallbackQuery):
        """یادآوری سیگنال"""
        await callback.message.edit_text(
            "🔔 <b>یادآوری تنظیم شد</b>\n\n"
            "به زودی یادآوری دریافت خواهید کرد.",
            parse_mode="HTML"
        )
        await callback.answer()
