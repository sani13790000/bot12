"""
=====================================================================
ÙÙØ¯ÙØ±ÙØ§Û Ú©ÙØªØ±Ù Ø±Ø¨Ø§Øª - Production Ready
=====================================================================
Ø§ÛÙ ÙØ§ÚÙÙ ÙØ³Ø¦ÙÙ ÙØ¯ÛØ±ÛØª Ø¯Ø³ØªÙØ±Ø§Øª Ú©ÙØªØ±ÙÛ Ø±Ø¨Ø§Øª Ø§Ø³Øª:
  /start  - Ø´Ø±ÙØ¹ Ø±Ø¨Ø§Øª
  /stop   - ØªÙÙÙ Ø±Ø¨Ø§Øª
  /status - ÙØ¶Ø¹ÛØª Ø±Ø¨Ø§Øª
  /close_all    - Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª
  /close_buys   - Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯
  /close_sells  - Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´
  /pause  - ÙÚ©Ø« ÙÙÙØª
  /resume - Ø§Ø¯Ø§ÙÙ

ÙÙÛØ³ÙØ¯Ù: MT5 Trading Team
ÙØ³Ø®Ù: 2.0.0
"""

import logging
import httpx
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from ..rbac import require_permission, UserPermission
from ..keyboards import get_main_keyboard, get_confirm_keyboard

logger = logging.getLogger(__name__)
router = Router()

# Ø¢Ø¯Ø±Ø³ API Ø¯Ø§Ø®ÙÛ
import os as _os
API_BASE_URL = _os.environ.get("API_BASE_URL", "http://localhost:8000") + "/api/v1"


def _get_headers(user_id: int) -> dict:
    """Ø³Ø§Ø®Øª ÙØ¯Ø± Ø§Ø­Ø±Ø§Ø² ÙÙÛØª Ø¨Ø±Ø§Û API"""
    return {"X-Telegram-User-Id": str(user_id), "Content-Type": "application/json"}


@router.message(Command("stop"))
@require_permission(UserPermission.ADMIN)
async def cmd_stop_bot(message: types.Message, state: FSMContext):
    """
    Ø¯Ø³ØªÙØ± /stop - ØªÙÙÙ Ú©Ø§ÙÙ Ø±Ø¨Ø§Øª
    ÙÙØ· Ø§Ø¯ÙÛÙâÙØ§ ÙÛâØªÙØ§ÙÙØ¯ Ø±Ø¨Ø§Øª Ø±Ø§ ÙØªÙÙÙ Ú©ÙÙØ¯.
    ÙØ¨Ù Ø§Ø² ØªÙÙÙØ ØªØ£ÛÛØ¯ Ø¯Ø±Ø®ÙØ§Ø³Øª ÙÛâØ´ÙØ¯.
    """
    keyboard = get_confirm_keyboard(action="stop_bot")
    await message.answer(
        "â ï¸ <b>ØªØ£ÛÛØ¯ ØªÙÙÙ Ø±Ø¨Ø§Øª</b>

"
        "Ø¢ÛØ§ Ø§Ø² ØªÙÙÙ Ú©Ø§ÙÙ Ø±Ø¨Ø§Øª Ø§Ø·ÙÛÙØ§Ù Ø¯Ø§Ø±ÛØ¯Ø
"
        "â ï¸ ØªÙØ§Ù ØªØ­ÙÛÙâÙØ§ Ù ÙØ¹Ø§ÙÙØ§Øª Ø¬Ø¯ÛØ¯ ÙØªÙÙÙ Ø®ÙØ§ÙÙØ¯ Ø´Ø¯.
"
        "ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² ÙÙÚÙØ§Ù ÙØ¹Ø§Ù ÙÛâÙØ§ÙÙØ¯.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_stop_bot")
@require_permission(UserPermission.ADMIN)
async def confirm_stop_bot(callback: types.CallbackQuery):
    """
    ØªØ£ÛÛØ¯ ØªÙÙÙ Ø±Ø¨Ø§Øª
    Ù¾Ø³ Ø§Ø² ØªØ£ÛÛØ¯Ø Ø³ÛÚ¯ÙØ§Ù ØªÙÙÙ Ø¨Ù Ø³Ø±ÙØ± Ø§Ø±Ø³Ø§Ù ÙÛâØ´ÙØ¯.
    """
    await callback.answer()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/control/stop",
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                await callback.message.edit_text(
                    "ð <b>Ø±Ø¨Ø§Øª ÙØªÙÙÙ Ø´Ø¯</b>

"
                    "â ØªÙØ§Ù ØªØ­ÙÛÙâÙØ§Û Ø¬Ø¯ÛØ¯ ÙØªÙÙÙ Ø´Ø¯ÙØ¯.
"
                    "ð ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² ÙÙÚÙØ§Ù ÙØ¹Ø§Ù ÙØ³ØªÙØ¯.
"
                    f"ð Ø²ÙØ§Ù ØªÙÙÙ: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    parse_mode="HTML"
                )
                logger.info(f"Ø±Ø¨Ø§Øª ØªÙØ³Ø· Ú©Ø§Ø±Ø¨Ø± {callback.from_user.id} ÙØªÙÙÙ Ø´Ø¯")
            else:
                await callback.message.edit_text(
                    f"â Ø®Ø·Ø§ Ø¯Ø± ØªÙÙÙ Ø±Ø¨Ø§Øª: {response.text}",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"Ø®Ø·Ø§ Ø¯Ø± ØªÙÙÙ Ø±Ø¨Ø§Øª: {e}")
        await callback.message.edit_text(
            f"â Ø®Ø·Ø§ Ø¯Ø± Ø§ØªØµØ§Ù Ø¨Ù Ø³Ø±ÙØ±: {str(e)[:100]}",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "cancel_stop_bot")
async def cancel_stop_bot(callback: types.CallbackQuery):
    """ÙØºÙ ØªÙÙÙ Ø±Ø¨Ø§Øª"""
    await callback.answer("â Ø¹ÙÙÛØ§Øª ÙØºÙ Ø´Ø¯")
    await callback.message.edit_text(
        "â ØªÙÙÙ Ø±Ø¨Ø§Øª ÙØºÙ Ø´Ø¯.",
        parse_mode="HTML"
    )


@router.message(Command("status"))
@require_permission(UserPermission.VIEW_STATUS)
async def cmd_status(message: types.Message):
    """
    Ø¯Ø³ØªÙØ± /status - ÙÙØ§ÛØ´ ÙØ¶Ø¹ÛØª ÙØ¹ÙÛ Ø±Ø¨Ø§Øª
    Ø´Ø§ÙÙ: ÙØ¶Ø¹ÛØª Ø§Ø¬Ø±Ø§Ø ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²Ø ÙÙØ¬ÙØ¯ÛØ Ø¹ÙÙÚ©Ø±Ø¯ Ø§ÙØ±ÙØ²
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/control/status",
                headers=_get_headers(message.from_user.id)
            )

            if response.status_code == 200:
                data = response.json()
                status = data.get("data", {})

                bot_status = "â ÙØ¹Ø§Ù" if status.get("is_running") else "ð ÙØªÙÙÙ"
                analysis_status = "â ÙØ¹Ø§Ù" if status.get("analysis_running") else "ð ÙØªÙÙÙ"

                text = (
                    f"ð <b>ÙØ¶Ø¹ÛØª Ø±Ø¨Ø§Øª</b>
"
                    f"{'â' * 30}
"
                    f"ð¤ <b>Ø±Ø¨Ø§Øª:</b> {bot_status}
"
                    f"ð§  <b>ØªØ­ÙÛÙ:</b> {analysis_status}
"
                    f"ð <b>ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²:</b> {status.get('open_trades', 0)}
"
                    f"ð° <b>ÙÙØ¬ÙØ¯Û:</b> {status.get('balance', 0):.2f}$
"
                    f"ð <b>Ø³ÙØ¯ Ø§ÙØ±ÙØ²:</b> {status.get('daily_profit', 0):+.2f}$
"
                    f"ð <b>ÙÛÙ Ø±ÛØª ÙÙØªÙ:</b> {status.get('weekly_winrate', 0):.1f}%
"
                    f"â¡ <b>Ø³Ø´Ù ÙØ¹Ø§Ù:</b> {status.get('active_session', 'ÙØ§ÙØ´Ø®Øµ')}
"
                    f"ð <b>Ø¢Ø®Ø±ÛÙ Ø¨Ø±ÙØ²Ø±Ø³Ø§ÙÛ:</b> {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC"
                )

                await message.answer(text, parse_mode="HTML", reply_markup=get_main_keyboard())
            else:
                await message.answer("â Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª ÙØ¶Ø¹ÛØª Ø³Ø±ÙØ±", parse_mode="HTML")

    except Exception as e:
        logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª ÙØ¶Ø¹ÛØª: {e}")
        await message.answer(f"â Ø®Ø·Ø§ Ø¯Ø± Ø§ØªØµØ§Ù Ø¨Ù Ø³Ø±ÙØ±", parse_mode="HTML")


@router.message(Command("close_all"))
@require_permission(UserPermission.CLOSE_TRADES)
async def cmd_close_all_trades(message: types.Message):
    """
    Ø¯Ø³ØªÙØ± /close_all - Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²
    Ø¨Ø±Ø§Û Ø¬ÙÙÚ¯ÛØ±Û Ø§Ø² Ø§Ø´ØªØ¨Ø§ÙØ ØªØ£ÛÛØ¯ Ø¯Ø±Ø®ÙØ§Ø³Øª ÙÛâØ´ÙØ¯.
    """
    keyboard = get_confirm_keyboard(action="close_all")
    await message.answer(
        "â ï¸ <b>ØªØ£ÛÛØ¯ Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª</b>

"
        "Ø¢ÛØ§ Ø§Ø² Ø¨Ø³ØªÙ ØªÙØ§Ù ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² Ø§Ø·ÙÛÙØ§Ù Ø¯Ø§Ø±ÛØ¯Ø
"
        "â ï¸ Ø§ÛÙ Ø¹ÙÙÛØ§Øª ÙØ§Ø¨Ù Ø¨Ø§Ø²Ú¯Ø´Øª ÙÛØ³Øª.",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_close_all")
@require_permission(UserPermission.CLOSE_TRADES)
async def confirm_close_all_trades(callback: types.CallbackQuery):
    """ØªØ£ÛÛØ¯ Ù Ø§Ø¬Ø±Ø§Û Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª"""
    await callback.answer()
    await callback.message.edit_text("â³ Ø¯Ø± Ø­Ø§Ù Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª...", parse_mode="HTML")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/trades/close-all",
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                data = response.json()
                result = data.get("data", {})
                closed = result.get("closed_count", 0)
                total_pl = result.get("total_profit_loss", 0)
                pl_sign = "+" if total_pl >= 0 else ""

                await callback.message.edit_text(
                    f"â <b>ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø³ØªÙ Ø´Ø¯ÙØ¯</b>

"
                    f"ð ØªØ¹Ø¯Ø§Ø¯ Ø¨Ø³ØªÙ Ø´Ø¯Ù: {closed}
"
                    f"ðµ ÙØªÛØ¬Ù Ú©Ù: {pl_sign}{total_pl:.2f}$
"
                    f"ð {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    f"â Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª: {response.text[:100]}",
                    parse_mode="HTML"
                )
    except Exception as e:
        logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª: {e}")
        await callback.message.edit_text(f"â Ø®Ø·Ø§: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("close_buys"))
@require_permission(UserPermission.CLOSE_TRADES)
async def cmd_close_buy_trades(message: types.Message):
    """
    Ø¯Ø³ØªÙØ± /close_buys - Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯
    """
    keyboard = get_confirm_keyboard(action="close_buys")
    await message.answer(
        "â ï¸ <b>ØªØ£ÛÛØ¯ Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯</b>

"
        "Ø¢ÛØ§ Ø§Ø² Ø¨Ø³ØªÙ ØªÙØ§Ù ÙØ¹Ø§ÙÙØ§Øª BUY Ø§Ø·ÙÛÙØ§Ù Ø¯Ø§Ø±ÛØ¯Ø",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_close_buys")
@require_permission(UserPermission.CLOSE_TRADES)
async def confirm_close_buys(callback: types.CallbackQuery):
    """ØªØ£ÛÛØ¯ Ù Ø§Ø¬Ø±Ø§Û Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯"""
    await callback.answer()
    await callback.message.edit_text("â³ Ø¯Ø± Ø­Ø§Ù Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯...", parse_mode="HTML")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/trades/close-by-direction",
                json={"direction": "BUY"},
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                await callback.message.edit_text(
                    f"â <b>ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯ Ø¨Ø³ØªÙ Ø´Ø¯ÙØ¯</b>

"
                    f"ð ØªØ¹Ø¯Ø§Ø¯: {data.get('closed_count', 0)}
"
                    f"ðµ ÙØªÛØ¬Ù: {data.get('total_profit_loss', 0):+.2f}$",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text("â Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª", parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"â Ø®Ø·Ø§: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("close_sells"))
@require_permission(UserPermission.CLOSE_TRADES)
async def cmd_close_sell_trades(message: types.Message):
    """
    Ø¯Ø³ØªÙØ± /close_sells - Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´
    """
    keyboard = get_confirm_keyboard(action="close_sells")
    await message.answer(
        "â ï¸ <b>ØªØ£ÛÛØ¯ Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´</b>

"
        "Ø¢ÛØ§ Ø§Ø² Ø¨Ø³ØªÙ ØªÙØ§Ù ÙØ¹Ø§ÙÙØ§Øª SELL Ø§Ø·ÙÛÙØ§Ù Ø¯Ø§Ø±ÛØ¯Ø",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "confirm_close_sells")
@require_permission(UserPermission.CLOSE_TRADES)
async def confirm_close_sells(callback: types.CallbackQuery):
    """ØªØ£ÛÛØ¯ Ù Ø§Ø¬Ø±Ø§Û Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´"""
    await callback.answer()
    await callback.message.edit_text("â³ Ø¯Ø± Ø­Ø§Ù Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´...", parse_mode="HTML")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/trades/close-by-direction",
                json={"direction": "SELL"},
                headers=_get_headers(callback.from_user.id)
            )

            if response.status_code == 200:
                data = response.json().get("data", {})
                await callback.message.edit_text(
                    f"â <b>ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´ Ø¨Ø³ØªÙ Ø´Ø¯ÙØ¯</b>

"
                    f"ð ØªØ¹Ø¯Ø§Ø¯: {data.get('closed_count', 0)}
"
                    f"ðµ ÙØªÛØ¬Ù: {data.get('total_profit_loss', 0):+.2f}$",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text("â Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª", parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"â Ø®Ø·Ø§: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("pause"))
@require_permission(UserPermission.ADMIN)
async def cmd_pause_bot(message: types.Message):
    """
    Ø¯Ø³ØªÙØ± /pause - ÙÚ©Ø« ÙÙÙØª Ø±Ø¨Ø§Øª (Ø¨Ø¯ÙÙ Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª)
    Ø±Ø¨Ø§Øª ÙØ¹Ø§ÙÙØ§Øª Ø¬Ø¯ÛØ¯ ÙÙÛâÚ¯ÛØ±Ø¯ Ø§ÙØ§ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² Ø±Ø§ ÙØ¯ÛØ±ÛØª ÙÛâÚ©ÙØ¯.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/control/pause",
                headers=_get_headers(message.from_user.id)
            )

            if response.status_code == 200:
                await message.answer(
                    "â¸ï¸ <b>Ø±Ø¨Ø§Øª Ø¯Ø± Ø­Ø§ÙØª ÙÚ©Ø«</b>

"
                    "â ÙØ¹Ø§ÙÙØ§Øª Ø¬Ø¯ÛØ¯ ÙØªÙÙÙ Ø´Ø¯ÙØ¯.
"
                    "ð ÙØ¯ÛØ±ÛØª ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² Ø§Ø¯Ø§ÙÙ Ø¯Ø§Ø±Ø¯.
"
                    "Ø¨Ø±Ø§Û Ø§Ø¯Ø§ÙÙ: /resume",
                    parse_mode="HTML"
                )
            else:
                await message.answer("â Ø®Ø·Ø§ Ø¯Ø± ÙÚ©Ø« Ø±Ø¨Ø§Øª", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"â Ø®Ø·Ø§: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("resume"))
@require_permission(UserPermission.ADMIN)
async def cmd_resume_bot(message: types.Message):
    """
    Ø¯Ø³ØªÙØ± /resume - Ø§Ø¯Ø§ÙÙ ÙØ¹Ø§ÙÛØª Ø±Ø¨Ø§Øª Ù¾Ø³ Ø§Ø² ÙÚ©Ø«
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_BASE_URL}/control/resume",
                headers=_get_headers(message.from_user.id)
            )

            if response.status_code == 200:
                await message.answer(
                    "â¶ï¸ <b>Ø±Ø¨Ø§Øª ÙØ¹Ø§Ù Ø´Ø¯</b>

"
                    "â Ø³ÛØ³ØªÙ Ø¯Ø± Ø­Ø§Ù Ø§Ø³Ú©Ù Ø¨Ø§Ø²Ø§Ø± Ø§Ø³Øª.
"
                    f"ð {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard()
                )
            else:
                await message.answer("â Ø®Ø·Ø§ Ø¯Ø± ÙØ¹Ø§ÙâØ³Ø§Ø²Û Ø±Ø¨Ø§Øª", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"â Ø®Ø·Ø§: {str(e)[:100]}", parse_mode="HTML")
