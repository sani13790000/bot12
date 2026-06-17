"""
ÙÙØ¯ÙØ±ÙØ§Û ØªØ­ÙÛÙ Ø¨Ø§Ø²Ø§Ø±

ÙÙÛØ³ÙØ¯Ù: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import httpx

from ..keyboards import (
    get_analysis_keyboard,
    get_timeframe_keyboard
)
from ..utils import format_analysis_result
from ....core.logger import get_logger
from ....core.config import settings
import os

# آدرس API از متغیر محیطی (برای Docker: http://api:8000، برای dev: http://localhost:8000)
_API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

logger = get_logger("telegram.handlers.analysis")


class AnalysisState(StatesGroup):
    """ÙØ¶Ø¹ÛØªâÙØ§Û ØªØ­ÙÛÙ"""
    waiting_symbol = State()
    waiting_timeframe = State()
    in_progress = State()


def register_analysis_handlers(dp: Dispatcher):
    """Ø«Ø¨Øª ÙÙØ¯ÙØ±ÙØ§Û ØªØ­ÙÛÙ"""

    @dp.message(F.text == "ð ØªØ­ÙÛÙ Ø¨Ø§Ø²Ø§Ø±")
    async def menu_analysis(message: types.Message, state: FSMContext):
        """ÙÙØ§ÛØ´ ÙÙÙÛ ØªØ­ÙÛÙ"""
        await state.set_state(AnalysisState.waiting_symbol)
        await message.answer(
            "ð <b>Ø§ÙØªØ®Ø§Ø¨ ÙÙØ§Ø¯</b>\n\n"
            "ÙÙØ§Ø¯ ÙÙØ±Ø¯ ÙØ¸Ø± Ø±Ø§ Ø§ÙØªØ®Ø§Ø¨ Ú©ÙÛØ¯:",
            reply_markup=get_analysis_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith("analyze_"))
    async def analyze_symbol(callback: types.CallbackQuery, state: FSMContext):
        """ØªØ­ÙÛÙ ÙÙØ§Ø¯ Ø§ÙØªØ®Ø§Ø¨ Ø´Ø¯Ù"""
        symbol = callback.data.split("_")[1]
        await state.update_data(symbol=symbol)
        await state.set_state(AnalysisState.waiting_timeframe)

        await callback.message.edit_text(
            f"ð ÙÙØ§Ø¯: <b>{symbol}</b>\n\n"
            "â° ØªØ§ÛÙâÙØ±ÛÙ Ø±Ø§ Ø§ÙØªØ®Ø§Ø¨ Ú©ÙÛØ¯:",
            reply_markup=get_timeframe_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "custom_symbol")
    async def custom_symbol(callback: types.CallbackQuery, state: FSMContext):
        """Ø¯Ø±Ø®ÙØ§Ø³Øª ÙÙØ§Ø¯ Ø³ÙØ§Ø±Ø´Û"""
        await state.set_state(AnalysisState.waiting_symbol)
        await callback.message.edit_text(
            "ð <b>ÙÙØ§Ø¯ Ø³ÙØ§Ø±Ø´Û</b>\n\n"
            "ÙÙØ§Ø¯ ÙÙØ±Ø¯ ÙØ¸Ø± Ø±Ø§ ÙØ§Ø±Ø¯ Ú©ÙÛØ¯:\n"
            "ÙØ«Ø§Ù: EURUSD, GBPUSD, XAUUSD",
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.message(AnalysisState.waiting_symbol)
    async def process_custom_symbol(message: types.Message, state: FSMContext):
        """Ù¾Ø±Ø¯Ø§Ø²Ø´ ÙÙØ§Ø¯ Ø³ÙØ§Ø±Ø´Û"""
        symbol = message.text.upper().strip()
        await state.update_data(symbol=symbol)

        await message.answer(
            f"ð ÙÙØ§Ø¯: <b>{symbol}</b>\n\n"
            "â° ØªØ§ÛÙâÙØ±ÛÙ Ø±Ø§ Ø§ÙØªØ®Ø§Ø¨ Ú©ÙÛØ¯:",
            reply_markup=get_timeframe_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(AnalysisState.waiting_timeframe)

    @dp.callback_query(F.data.startswith("tf_"), AnalysisState.waiting_timeframe)
    async def process_timeframe(callback: types.CallbackQuery, state: FSMContext):
        """Ù¾Ø±Ø¯Ø§Ø²Ø´ ØªØ§ÛÙâÙØ±ÛÙ Ù Ø´Ø±ÙØ¹ ØªØ­ÙÛÙ"""
        timeframe = callback.data.split("_")[1]
        data = await state.get_data()
        symbol = data.get("symbol")

        await callback.message.edit_text(
            f"ð <b>Ø¯Ø± Ø­Ø§Ù ØªØ­ÙÛÙ...</b>\n\n"
            f"ÙÙØ§Ø¯: {symbol}\n"
            f"ØªØ§ÛÙâÙØ±ÛÙ: {timeframe}",
            parse_mode="HTML"
        )

        try:
            # ÙØ±Ø§Ø®ÙØ§ÙÛ API ØªØ­ÙÛÙ
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.API_BASE_URL}/api/analysis/full",
                    params={
                        "symbol": symbol,
                        "timeframe": timeframe
                    },
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                analysis_text = format_analysis_result(result)
                await callback.message.edit_text(
                    analysis_text,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "â <b>Ø®Ø·Ø§ Ø¯Ø± ØªØ­ÙÛÙ</b>\n\n"
                    "ÙØ·ÙØ§Ù Ø¯ÙØ¨Ø§Ø±Ù ØªÙØ§Ø´ Ú©ÙÛØ¯.",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± ØªØ­ÙÛÙ: {e}")
            await callback.message.edit_text(
                "â <b>Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±ØªØ¨Ø§Ø· Ø¨Ø§ Ø³Ø±ÙØ±</b>\n\n"
                "ÙØ·ÙØ§Ù Ø¯ÙØ¨Ø§Ø±Ù ØªÙØ§Ø´ Ú©ÙÛØ¯.",
                parse_mode="HTML"
            )

        await state.clear()
        await callback.answer()
