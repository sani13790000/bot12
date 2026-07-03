"""
backend/telegram/handlers/control.py
Galaxy Vast AI - Bot Control Telegram Handlers

Commands: /start_bot /stop_bot /pause_bot /resume_bot /bot_status /kill
"""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
router = Router()


def _confirm_kb(action: str) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="بله، مطمئنم",  callback_data=f"confirm:{action}")
    builder.button(text="خیر، انصراف", callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


@router.message(Command("bot_status"))
async def cmd_bot_status(message: types.Message) -> None:
    try:
        from backend.services.trade_service import TradeService
        s = await TradeService().get_bot_status()
        emoji = {"RUNNING": "🟢", "PAUSED": "🟡", "STOPPED": "🔴"}.get(s.get("state", ""), "⚪")
        lines = [
            f"{emoji} <b>وضعیت ربات</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"<b>حالت:</b>        {s.get('state', 'نامشخص')}",
            f"<b>معاملات باز:</b> {s.get('open_trades', 0)}",
            f"<b>سود امروز:</b>   {s.get('today_pnl', 0):.2f}$",
            f"<b>Kill Switch:</b> {'فعال' if s.get('kill_switch') else 'غیرفعال'}",
        ]
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


@router.message(Command("stop_bot"))
async def cmd_stop_bot(message: types.Message) -> None:
    await message.answer(
        "<b>تایید توقف ربات</b>\nآیا مطمئنید؟\nمعاملات باز <b>بسته نخواهند شد</b>.",
        parse_mode="HTML", reply_markup=_confirm_kb("stop_bot"),
    )


@router.callback_query(lambda c: c.data == "confirm:stop_bot")
async def on_confirm_stop(callback: types.CallbackQuery) -> None:
    await callback.answer()
    try:
        from backend.services.trade_service import TradeService
        await TradeService().stop_bot()
        await callback.message.edit_text("<b>ربات متوقف شد</b>\n/start_bot برای راه‌اندازی", parse_mode="HTML")
    except Exception as exc:
        await callback.message.edit_text(f"خطا: {exc}")


@router.message(Command("start_bot"))
async def cmd_start_bot(message: types.Message) -> None:
    try:
        from backend.services.trade_service import TradeService
        await TradeService().start_bot()
        await message.answer("<b>ربات راه‌اندازی شد</b>\nآماده دریافت سیگنال.", parse_mode="HTML")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


@router.message(Command("pause_bot"))
async def cmd_pause_bot(message: types.Message) -> None:
    try:
        from backend.services.trade_service import TradeService
        await TradeService().pause_bot()
        await message.answer("<b>ربات متوقف شد (موقت)</b>\n/resume_bot برای ادامه", parse_mode="HTML")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


@router.message(Command("resume_bot"))
async def cmd_resume_bot(message: types.Message) -> None:
    try:
        from backend.services.trade_service import TradeService
        await TradeService().resume_bot()
        await message.answer("<b>ربات از سر گرفته شد</b>", parse_mode="HTML")
    except Exception as exc:
        await message.answer(f"خطا: {exc}")


@router.message(Command("kill"))
async def cmd_kill(message: types.Message) -> None:
    if not getattr(message.bot, "_user_data", {}).get("is_admin"):
        await message.answer("این دستور فقط برای مدیران است")
        return
    await message.answer(
        "<b>تایید KILL SWITCH</b>\nتمام معاملات بسته می‌شوند!",
        parse_mode="HTML", reply_markup=_confirm_kb("kill_switch"),
    )


@router.callback_query(lambda c: c.data == "confirm:kill_switch")
async def on_confirm_kill(callback: types.CallbackQuery) -> None:
    await callback.answer("در حال اجرا...")
    try:
        from backend.risk.kill_switch import KillSwitch
        await KillSwitch().activate(reason=f"Telegram KILL by {callback.from_user.id}")
        await callback.message.edit_text("<b>KILL SWITCH فعال شد</b>\nتمام معاملات بسته شدند.", parse_mode="HTML")
        logger.critical("KILL SWITCH activated by %s", callback.from_user.id)
    except Exception as exc:
        await callback.message.edit_text(f"خطا: {exc}")


@router.callback_query(lambda c: c.data == "cancel")
async def on_cancel(callback: types.CallbackQuery) -> None:
    await callback.answer("لغو شد")
    await callback.message.edit_text("عملیات لغو شد")
