"""
هندلرهای تحلیل بازار

نویسنده: MT5 Trading Team
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

logger = get_logger("telegram.handlers.analysis")


class AnalysisState(StatesGroup):
    """وضعیت‌های تحلیل"""
    waiting_symbol = State()
    waiting_timeframe = State()
    in_progress = State()


def register_analysis_handlers(dp: Dispatcher):
    """ثبت هندلرهای تحلیل"""

    @dp.message(F.text == "📊 تحلیل بازار")
    async def menu_analysis(message: types.Message, state: FSMContext):
        """نمایش منوی تحلیل"""
        await state.set_state(AnalysisState.waiting_symbol)
        await message.answer(
            "📊 <b>انتخاب نماد</b>\n\n"
            "نماد مورد نظر را انتخاب کنید:",
            reply_markup=get_analysis_keyboard(),
            parse_mode="HTML"
        )

    @dp.callback_query(F.data.startswith("analyze_"))
    async def analyze_symbol(callback: types.CallbackQuery, state: FSMContext):
        """تحلیل نماد انتخاب شده"""
        symbol = callback.data.split("_")[1]
        await state.update_data(symbol=symbol)
        await state.set_state(AnalysisState.waiting_timeframe)

        await callback.message.edit_text(
            f"📊 نماد: <b>{symbol}</b>\n\n"
            "⏰ تایم‌فریم را انتخاب کنید:",
            reply_markup=get_timeframe_keyboard(),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "custom_symbol")
    async def custom_symbol(callback: types.CallbackQuery, state: FSMContext):
        """درخواست نماد سفارشی"""
        await state.set_state(AnalysisState.waiting_symbol)
        await callback.message.edit_text(
            "🔍 <b>نماد سفارشی</b>\n\n"
            "نماد مورد نظر را وارد کنید:\n"
            "مثال: EURUSD, GBPUSD, XAUUSD",
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.message(AnalysisState.waiting_symbol)
    async def process_custom_symbol(message: types.Message, state: FSMContext):
        """پردازش نماد سفارشی"""
        symbol = message.text.upper().strip()
        await state.update_data(symbol=symbol)

        await message.answer(
            f"📊 نماد: <b>{symbol}</b>\n\n"
            "⏰ تایم‌فریم را انتخاب کنید:",
            reply_markup=get_timeframe_keyboard(),
            parse_mode="HTML"
        )
        await state.set_state(AnalysisState.waiting_timeframe)

    @dp.callback_query(F.data.startswith("tf_"), AnalysisState.waiting_timeframe)
    async def process_timeframe(callback: types.CallbackQuery, state: FSMContext):
        """پردازش تایم‌فریم و شروع تحلیل"""
        timeframe = callback.data.split("_")[1]
        data = await state.get_data()
        symbol = data.get("symbol")

        await callback.message.edit_text(
            f"📊 <b>در حال تحلیل...</b>\n\n"
            f"نماد: {symbol}\n"
            f"تایم‌فریم: {timeframe}",
            parse_mode="HTML"
        )

        try:
            # فراخوانی API تحلیل
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"http://localhost:8000/api/analysis/full",
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
                    "❌ <b>خطا در تحلیل</b>\n\n"
                    "لطفاً دوباره تلاش کنید.",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"خطا در تحلیل: {e}")
            await callback.message.edit_text(
                "❌ <b>خطا در ارتباط با سرور</b>\n\n"
                "لطفاً دوباره تلاش کنید.",
                parse_mode="HTML"
            )

        await state.clear()
        await callback.answer()
