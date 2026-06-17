"""
ÙÙØ¯ÙØ±ÙØ§Û Ø³ÛÚ¯ÙØ§ÙâÙØ§

ÙÙÛØ³ÙØ¯Ù: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
import httpx

from ..keyboards import get_signals_keyboard, get_signal_action_keyboard
from ..utils import format_signal_card
import os as _os
from ....core.logger import get_logger

_API_BASE_URL = _os.environ.get("API_BASE_URL", "http://localhost:8000")

logger = get_logger("telegram.handlers.signals")


def register_signal_handlers(dp: Dispatcher):
    """Ø«Ø¨Øª ÙÙØ¯ÙØ±ÙØ§Û Ø³ÛÚ¯ÙØ§ÙâÙØ§"""

    @dp.message(F.text == "ð Ø³ÛÚ¯ÙØ§ÙâÙØ§")
    async def menu_signals(message: types.Message):
        """ÙÙØ§ÛØ´ ÙÙÙÛ Ø³ÛÚ¯ÙØ§ÙâÙØ§"""
        await message.answer(
            "ð <b>ÙØ¯ÛØ±ÛØª Ø³ÛÚ¯ÙØ§ÙâÙØ§</b>\n\n"
            "Ú¯Ø²ÛÙÙ ÙÙØ±Ø¯ ÙØ¸Ø± Ø±Ø§ Ø§ÙØªØ®Ø§Ø¨ Ú©ÙÛØ¯:",
            reply_markup=get_signals_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data == "signals_active")
    async def show_active_signals(callback: types.CallbackQuery):
        """ÙÙØ§ÛØ´ Ø³ÛÚ¯ÙØ§ÙâÙØ§Û ÙØ¹Ø§Ù"""
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
                        "ð­ <b>Ø³ÛÚ¯ÙØ§ÙâÙØ§Û ÙØ¹Ø§Ù</b>\n\n"
                        "Ø¯Ø± Ø­Ø§Ù Ø­Ø§Ø¶Ø± Ø³ÛÚ¯ÙØ§Ù ÙØ¹Ø§ÙÛ ÙØ¬ÙØ¯ ÙØ¯Ø§Ø±Ø¯.",
                        parse_mode="HTML"
                    )
                else:
                    for signal in signals[:3]:  # Ø­Ø¯Ø§Ú©Ø«Ø± 3 Ø³ÛÚ¯ÙØ§Ù
                        text = format_signal_card(signal)
                        await callback.message.answer(
                            text,
                            reply_markup=get_signal_action_keyboard(signal["id"]),
                            parse_mode="HTML"
                        )
                    await callback.message.delete()
            else:
                await callback.message.edit_text(
                    "â Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª Ø³ÛÚ¯ÙØ§ÙâÙØ§",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª Ø³ÛÚ¯ÙØ§ÙâÙØ§: {e}")
            await callback.message.edit_text(
                "â Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙØ±",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "signals_history")
    async def show_signal_history(callback: types.CallbackQuery):
        """ÙÙØ§ÛØ´ ØªØ§Ø±ÛØ®ÚÙ Ø³ÛÚ¯ÙØ§ÙâÙØ§"""
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
                        "ð­ <b>ØªØ§Ø±ÛØ®ÚÙ Ø³ÛÚ¯ÙØ§ÙâÙØ§</b>\n\n"
                        "ÙÛÚ Ø³ÛÚ¯ÙØ§ÙÛ Ø«Ø¨Øª ÙØ´Ø¯Ù.",
                        parse_mode="HTML"
                    )
                else:
                    text = "ð <b>ØªØ§Ø±ÛØ®ÚÙ Ø³ÛÚ¯ÙØ§ÙâÙØ§</b>\n\n"

                    wins = 0
                    losses = 0

                    for signal in signals[:10]:
                        status_emoji = {
                            "executed": "â",
                            "expired": "â°",
                            "skipped": "â­"
                        }.get(signal.get("status"), "â")

                        direction_emoji = "ð¢" if signal.get("direction") == "buy" else "ð´"

                        result_text = ""
                        if signal.get("result"):
                            if signal["result"] == "win":
                                wins += 1
                                result_text = " ð°"
                            elif signal["result"] == "loss":
                                losses += 1
                                result_text = " ð"

                        text += (
                            f"{status_emoji} {direction_emoji} <b>{signal.get('symbol')}</b> "
                            f"- Ø§ÙØªÛØ§Ø²: {signal.get('total_score', 0):.0f}{result_text}\n"
                        )

                    text += f"\nð Ø¨Ø±ÙØ¯Ù: {wins} | Ø¨Ø§Ø²ÙØ¯Ù: {losses}"
                    await callback.message.edit_text(text, parse_mode="HTML")
            else:
                await callback.message.edit_text(
                    "â Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª ØªØ§Ø±ÛØ®ÚÙ",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª ØªØ§Ø±ÛØ®ÚÙ: {e}")
            await callback.message.edit_text(
                "â Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙØ±",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_execute_"))
    async def execute_signal(callback: types.CallbackQuery):
        """Ø§Ø¬Ø±Ø§Û Ø³ÛÚ¯ÙØ§Ù"""
        signal_id = callback.data.split("_")[2]

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{_API_BASE_URL}/api/signals/{signal_id}/execute",
                    timeout=30.0
                )

            if response.status_code == 200:
                await callback.message.edit_text(
                    "â <b>Ø³ÛÚ¯ÙØ§Ù Ø§Ø¬Ø±Ø§ Ø´Ø¯!</b>\n\n"
                    "ÙØ¹Ø§ÙÙÙ Ø¨Ø§ ÙÙÙÙÛØª Ø¨Ø§Ø² Ø´Ø¯.",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "â Ø®Ø·Ø§ Ø¯Ø± Ø§Ø¬Ø±Ø§Û Ø³ÛÚ¯ÙØ§Ù",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø§Ø¬Ø±Ø§Û Ø³ÛÚ¯ÙØ§Ù: {e}")
            await callback.message.edit_text(
                "â Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙØ±",
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_skip_"))
    async def skip_signal(callback: types.CallbackQuery):
        """Ø±Ø¯ Ú©Ø±Ø¯Ù Ø³ÛÚ¯ÙØ§Ù"""
        signal_id = callback.data.split("_")[2]

        await callback.message.edit_text(
            "â­ <b>Ø³ÛÚ¯ÙØ§Ù Ø±Ø¯ Ø´Ø¯</b>",
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("signal_remind_"))
    async def remind_signal(callback: types.CallbackQuery):
        """ÛØ§Ø¯Ø¢ÙØ±Û Ø³ÛÚ¯ÙØ§Ù"""
        await callback.message.edit_text(
            "ð <b>ÛØ§Ø¯Ø¢ÙØ±Û ØªÙØ¸ÛÙ Ø´Ø¯</b>\n\n"
            "Ø¨Ù Ø²ÙØ¯Û ÛØ§Ø¯Ø¢ÙØ±Û Ø¯Ø±ÛØ§ÙØª Ø®ÙØ§ÙÛØ¯ Ú©Ø±Ø¯.",
            parse_mode="HTML"
        )
        await callback.answer()
