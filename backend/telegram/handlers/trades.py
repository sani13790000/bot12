"""
ÙÙØ¯ÙØ±ÙØ§Û ÙØ¹Ø§ÙÙØ§Øª

Ø¨Ø§ Authorization Ù Rate Limiting.

ÙÙÛØ³ÙØ¯Ù: MT5 Trading Team
"""

from aiogram import Dispatcher, types, F
from aiogram.fsm.context import FSMContext
import httpx

from ..keyboards import get_trades_keyboard, get_confirm_keyboard, get_back_keyboard
from ..utils import format_trade_list, format_trade_detail, format_error_message
from ..auth import (
    require_permission, require_role,
    Permission, UserRole
)
from ..rbac_service import rbac_service
from ....core.logger import get_logger
from ....core.config import settings
from ....services.audit_service import audit_service, AuditAction

logger = get_logger("telegram.handlers.trades")


# API endpoint Ù¾Ø§ÛÙ
import os as _os
API_BASE = _os.environ.get("API_BASE_URL", f"http://localhost:{settings.API_PORT}") + settings.API_PREFIX


def register_trade_handlers(dp: Dispatcher):
    """Ø«Ø¨Øª ÙÙØ¯ÙØ±ÙØ§Û ÙØ¹Ø§ÙÙØ§Øª"""

    # --------------------------------------------------
    # ÙÙÙÛ ÙØ¹Ø§ÙÙØ§Øª
    # --------------------------------------------------

    @dp.message(F.text == "ð ÙØ¹Ø§ÙÙØ§Øª ÙÙ")
    async def menu_trades(message: types.Message):
        """ÙÙØ§ÛØ´ ÙÙÙÛ ÙØ¹Ø§ÙÙØ§Øª"""
        # Ø¨Ø±Ø±Ø³Û Ø«Ø¨Øª Ú©Ø§Ø±Ø¨Ø±
        user = await rbac_service.get_user_by_telegram_id(message.from_user.id)
        if not user:
            await message.answer(
                "â ï¸ Ø¨Ø±Ø§Û Ø¯Ø³ØªØ±Ø³Û Ø¨Ù ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§ÛØ¯ Ø«Ø¨ØªâÙØ§Ù Ú©ÙÛØ¯.",
                parse_mode="HTML"
            )
            return

        # ÙÙÙÛ ÙÙØ§Ø³Ø¨ Ø¨Ø±Ø§Û ÙÙØ´
        role = await rbac_service.get_user_role(message.from_user.id)

        if role and role.value in ["trader", "admin", "super_admin"]:
            await message.answer(
                "ð <b>ÙØ¯ÛØ±ÛØª ÙØ¹Ø§ÙÙØ§Øª</b>\n\n"
                "Ú¯Ø²ÛÙÙ ÙÙØ±Ø¯ ÙØ¸Ø± Ø±Ø§ Ø§ÙØªØ®Ø§Ø¨ Ú©ÙÛØ¯:",
                reply_markup=get_trades_keyboard(full=True),
                parse_mode="HTML"
            )
        else:
            # ÙÙØ· ÙØ´Ø§ÙØ¯Ù Ø¨Ø±Ø§Û user
            await message.answer(
                "ð <b>ÙØ´Ø§ÙØ¯Ù ÙØ¹Ø§ÙÙØ§Øª</b>\n\n"
                "Ø´ÙØ§ ÙÙØ· ÙÛâØªÙØ§ÙÛØ¯ ÙØ¹Ø§ÙÙØ§Øª Ø±Ø§ ÙØ´Ø§ÙØ¯Ù Ú©ÙÛØ¯.\n"
                "Ø¨Ø±Ø§Û ÙØ¹Ø§ÙÙÙ Ø¨Ù ÙÙØ´ trader Ø§Ø±ØªÙØ§ ÛØ§Ø¨ÛØ¯.",
                reply_markup=get_trades_keyboard(full=False),
                parse_mode="HTML"
            )

    # --------------------------------------------------
    # ÙØ´Ø§ÙØ¯Ù ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_open")
    async def show_open_trades(callback: types.CallbackQuery):
        """ÙÙØ§ÛØ´ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "â ï¸ Ø«Ø¨Øª ÙØ´Ø¯Ù",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/trade-report/open",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                trades = result.get("data", {}).get("positions", [])

                if not trades:
                    await callback.message.edit_text(
                        "ð­ <b>ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²</b>\n\n"
                        "ÙÛÚ ÙØ¹Ø§ÙÙÙâØ§Û Ø¨Ø§Ø² ÙÛØ³Øª.",
                        parse_mode="HTML"
                    )
                else:
                    text = format_trade_list(trades, "ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø²")
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML"
                    )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª ÙØ¹Ø§ÙÙØ§Øª: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # ØªØ§Ø±ÛØ®ÚÙ ÙØ¹Ø§ÙÙØ§Øª
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_history")
    async def show_trade_history(callback: types.CallbackQuery):
        """ÙÙØ§ÛØ´ ØªØ§Ø±ÛØ®ÚÙ ÙØ¹Ø§ÙÙØ§Øª"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "â ï¸ Ø«Ø¨Øª ÙØ´Ø¯Ù",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/trade-report/",
                    params={"limit": 20},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                trades = result.get("data", {}).get("trades", [])

                if not trades:
                    await callback.message.edit_text(
                        "ð­ <b>ØªØ§Ø±ÛØ®ÚÙ ÙØ¹Ø§ÙÙØ§Øª</b>\n\n"
                        "ÙÛÚ ÙØ¹Ø§ÙÙÙâØ§Û Ø«Ø¨Øª ÙØ´Ø¯Ù.",
                        parse_mode="HTML"
                    )
                else:
                    text = format_trade_list(trades, "ØªØ§Ø±ÛØ®ÚÙ ÙØ¹Ø§ÙÙØ§Øª")
                    await callback.message.edit_text(
                        text,
                        parse_mode="HTML"
                    )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª ØªØ§Ø±ÛØ®ÚÙ: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª (Ø­Ø³Ø§Ø³ - ÙÛØ§Ø² Ø¨Ù permission)
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_close_all")
    async def confirm_close_all(callback: types.CallbackQuery):
        """ØªØ£ÛÛØ¯ Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª"""
        # Ø¨Ø±Ø±Ø³Û Ø¯Ø³ØªØ±Ø³Û
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.CLOSE_ALL_TRADES
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "ð« Ø¯Ø³ØªØ±Ø³Û ØºÛØ±ÙØ¬Ø§Ø²"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "â ï¸ <b>ÙØ´Ø¯Ø§Ø±!</b>\n\n"
            "Ø¢ÛØ§ ÙØ·ÙØ¦Ù ÙØ³ØªÛØ¯ Ú©Ù ÙÛâØ®ÙØ§ÙÛØ¯\n"
            "ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø§Ø² Ø±Ø§ Ø¨Ø¨ÙØ¯ÛØ¯Ø\n\n"
            "Ø§ÛÙ Ø¹ÙÙÛØ§Øª ÙØ§Ø¨Ù Ø¨Ø§Ø²Ú¯Ø´Øª ÙÛØ³Øª!",
            reply_markup=get_confirm_keyboard("close_all"),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "confirm_close_all")
    async def execute_close_all(callback: types.CallbackQuery):
        """Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "â ï¸ Ø®Ø·Ø§ Ø¯Ø± Ø§Ø­Ø±Ø§Ø² ÙÙÛØª",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Ø«Ø¨Øª audit log
        await audit_service.log_trade(
            user_id=user.get("id"),
            trade_id="all",
            action="close",
            symbol="ALL",
            direction="all"
        )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE}/trade-report/close-all",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})

                closed_count = data.get("closed_count", 0)
                total_profit = data.get("total_profit", 0)

                await callback.message.edit_text(
                    f"â <b>ÙØ¹Ø§ÙÙØ§Øª Ø¨Ø³ØªÙ Ø´Ø¯ÙØ¯</b>\n\n"
                    f"ð ØªØ¹Ø¯Ø§Ø¯: {closed_count}\n"
                    f"ð° Ø³ÙØ¯/Ø¶Ø±Ø±: ${total_profit:.2f}",
                    parse_mode="HTML"
                )

                logger.info(
                    f"{closed_count} ÙØ¹Ø§ÙÙÙ ØªÙØ³Ø· {user.get('id')} Ø¨Ø³ØªÙ Ø´Ø¯"
                )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    @dp.callback_query(F.data == "cancel_close_all")
    async def cancel_close_all(callback: types.CallbackQuery):
        """ÙØºÙ Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª"""
        await callback.message.edit_text(
            "â Ø¹ÙÙÛØ§Øª ÙØºÙ Ø´Ø¯.",
            parse_mode="HTML"
        )
        await callback.answer()

    # --------------------------------------------------
    # Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_close_buy")
    async def confirm_close_buy(callback: types.CallbackQuery):
        """ØªØ£ÛÛØ¯ Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯"""
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.CLOSE_BUY_TRADES
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "ð« Ø¯Ø³ØªØ±Ø³Û ØºÛØ±ÙØ¬Ø§Ø²"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "â ï¸ <b>Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯</b>\n\n"
            "Ø¢ÛØ§ ÙØ·ÙØ¦Ù ÙØ³ØªÛØ¯Ø",
            reply_markup=get_confirm_keyboard("close_buy"),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "confirm_close_buy")
    async def execute_close_buy(callback: types.CallbackQuery):
        """Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text("â ï¸ Ø®Ø·Ø§", parse_mode="HTML")
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE}/trade-report/close-all",
                    params={"direction": "buy"},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})

                await callback.message.edit_text(
                    f"â <b>ÙØ¹Ø§ÙÙØ§Øª Ø®Ø±ÛØ¯ Ø¨Ø³ØªÙ Ø´Ø¯ÙØ¯</b>\n\n"
                    f"ð ØªØ¹Ø¯Ø§Ø¯: {data.get('closed_count', 0)}\n"
                    f"ð° Ø³ÙØ¯/Ø¶Ø±Ø±: ${data.get('total_profit', 0):.2f}",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ Ø®Ø±ÛØ¯ÙØ§: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´
    # --------------------------------------------------

    @dp.callback_query(F.data == "trades_close_sell")
    async def confirm_close_sell(callback: types.CallbackQuery):
        """ØªØ£ÛÛØ¯ Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´"""
        check = await rbac_service.check_permission(
            callback.from_user.id,
            Permission.CLOSE_SELL_TRADES
        )

        if not check.get("allowed"):
            await callback.message.edit_text(
                check.get("message", "ð« Ø¯Ø³ØªØ±Ø³Û ØºÛØ±ÙØ¬Ø§Ø²"),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        await callback.message.edit_text(
            "â ï¸ <b>Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´</b>\n\n"
            "Ø¢ÛØ§ ÙØ·ÙØ¦Ù ÙØ³ØªÛØ¯Ø",
            reply_markup=get_confirm_keyboard("close_sell"),
            parse_mode="HTML"
        )
        await callback.answer()

    @dp.callback_query(F.data == "confirm_close_sell")
    async def execute_close_sell(callback: types.CallbackQuery):
        """Ø¨Ø³ØªÙ ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´"""
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)
        if not user:
            await callback.message.edit_text("â ï¸ Ø®Ø·Ø§", parse_mode="HTML")
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{API_BASE}/trade-report/close-all",
                    params={"direction": "sell"},
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=30.0
                )

            if response.status_code == 200:
                result = response.json()
                data = result.get("data", {})

                await callback.message.edit_text(
                    f"â <b>ÙØ¹Ø§ÙÙØ§Øª ÙØ±ÙØ´ Ø¨Ø³ØªÙ Ø´Ø¯ÙØ¯</b>\n\n"
                    f"ð ØªØ¹Ø¯Ø§Ø¯: {data.get('closed_count', 0)}\n"
                    f"ð° Ø³ÙØ¯/Ø¶Ø±Ø±: ${data.get('total_profit', 0):.2f}",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    format_error_message("server"),
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø³ØªÙ ÙØ±ÙØ´âÙØ§: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # Ø¬Ø²Ø¦ÛØ§Øª ÙØ¹Ø§ÙÙÙ
    # --------------------------------------------------

    @dp.callback_query(F.data.startswith("trade_"))
    async def show_trade_detail(callback: types.CallbackQuery):
        """Ø¬Ø²Ø¦ÛØ§Øª ÙØ¹Ø§ÙÙÙ"""
        trade_id = callback.data.split("_")[1]
        user = await rbac_service.get_user_by_telegram_id(callback.from_user.id)

        if not user:
            await callback.message.edit_text("â ï¸ Ø®Ø·Ø§", parse_mode="HTML")
            await callback.answer()
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{API_BASE}/trade-report/{trade_id}",
                    headers={"Authorization": f"Bearer {user.get('id')}"},
                    timeout=10.0
                )

            if response.status_code == 200:
                result = response.json()
                trade = result.get("data", {})

                text = format_trade_detail(trade)
                await callback.message.edit_text(
                    text,
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text(
                    "â ÙØ¹Ø§ÙÙÙ ÛØ§ÙØª ÙØ´Ø¯",
                    parse_mode="HTML"
                )

        except Exception as e:
            logger.error(f"Ø®Ø·Ø§ Ø¯Ø± Ø¯Ø±ÛØ§ÙØª Ø¬Ø²Ø¦ÛØ§Øª: {e}")
            await callback.message.edit_text(
                format_error_message("server"),
                parse_mode="HTML"
            )

        await callback.answer()

    # --------------------------------------------------
    # Ø¯Ø³ØªÙØ±Ø§Øª ÙØªÙÛ
    # --------------------------------------------------

    @dp.message(F.text.regexp(r"^/close_all"))
    async def cmd_close_all(message: types.Message):
        """Ø¯Ø³ØªÙØ± Ø¨Ø³ØªÙ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª"""
        check = await rbac_service.check_permission(
            message.from_user.id,
            Permission.CLOSE_ALL_TRADES
        )

        if not check.get("allowed"):
            await message.answer(
                check.get("message", "ð« Ø¯Ø³ØªØ±Ø³Û ØºÛØ±ÙØ¬Ø§Ø²"),
                parse_mode="HTML"
            )
            return

        # ÙÙØ§ÛØ´ ØªØ£ÛÛØ¯
        await message.answer(
            "â ï¸ <b>ÙØ´Ø¯Ø§Ø±!</b>\n\n"
            "Ø¢ÛØ§ ÙØ·ÙØ¦Ù ÙØ³ØªÛØ¯ Ú©Ù ÙÛâØ®ÙØ§ÙÛØ¯ ÙÙÙ ÙØ¹Ø§ÙÙØ§Øª Ø±Ø§ Ø¨Ø¨ÙØ¯ÛØ¯Ø\n\n"
            "Ø¨Ø±Ø§Û ØªØ£ÛÛØ¯ /yes Ø±Ø§ Ø¨ÙØ±Ø³ØªÛØ¯.",
            parse_mode="HTML"
        )
