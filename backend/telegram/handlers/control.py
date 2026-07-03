"""
backend/telegram/handlers/control.py
Bot control commands for Telegram (stop/pause/resume/close trades).
Version: 2.0.0
"""
from __future__ import annotations
import logging
import httpx
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)
router = Router(name="control")
_API_BASE = getattr(settings, "API_BASE_URL", "http://api:8000")


def get_confirm_keyboard(action: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="\u2705 \u0628\u0644\u0647", callback_data=f"confirm_{action}"),
        InlineKeyboardButton(text="\u274c \u0644\u063a\u0648", callback_data="cancel"),
    ]])


def get_main_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/status"), KeyboardButton(text="/pause")],
            [KeyboardButton(text="/resume"), KeyboardButton(text="/close_all")],
        ],
        resize_keyboard=True
    )


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "\U0001f30c <b>Galaxy Vast Trading Bot</b>\n\n\u0631\u0628\u0627\u062a \u0645\u0639\u0627\u0645\u0644\u0627\u062a\u06cc \u0641\u0639\u0627\u0644 \u0627\u0633\u062a.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


@router.message(Command("stop"))
async def cmd_stop_bot(message: types.Message, state: FSMContext):
    await message.answer(
        "\u26a0\ufe0f \u0622\u06cc\u0627 \u0645\u0637\u0645\u0626\u0646 \u0647\u0633\u062a\u06cc\u062f \u06a9\u0647 \u0645\u06cc\u200c\u062e\u0648\u0627\u0647\u06cc\u062f \u0631\u0628\u0627\u062a \u0631\u0627 \u0645\u062a\u0648\u0642\u0641 \u06a9\u0646\u06cc\u062f\u061f",
        parse_mode="HTML",
        reply_markup=get_confirm_keyboard(action="stop_bot")
    )


@router.callback_query(F.data == "confirm_stop_bot")
async def confirm_stop_bot(callback: types.CallbackQuery):
    await callback.answer()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{_API_BASE}/api/v1/control/stop")
            if response.status_code == 200:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                await callback.message.edit_text(
                    f"\U0001f6d1 <b>\u0631\u0628\u0627\u062a \u0645\u062a\u0648\u0642\u0641 \u0634\u062f</b>\n\n\u23f0 \u0632\u0645\u0627\u0646: {ts} UTC",
                    parse_mode="HTML"
                )
            else:
                await callback.message.edit_text("\u274c \u062e\u0637\u0627 \u062f\u0631 \u0645\u062a\u0648\u0642\u0641 \u06a9\u0631\u062f\u0646 \u0631\u0628\u0627\u062a", parse_mode="HTML")
    except Exception as e:
        await callback.message.edit_text(f"\u274c \u062e\u0637\u0627: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{_API_BASE}/api/v1/health")
            if response.status_code == 200:
                data = response.json()
                mode = data.get("mode", "UNKNOWN")
                status_str = data.get("status", "unknown")
                ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
                await message.answer(
                    f"\U0001f4ca <b>\u0648\u0636\u0639\u06cc\u062a \u0631\u0628\u0627\u062a</b>\n\n\u25cf \u0648\u0636\u0639\u06cc\u062a: {status_str}\n\u25cf \u062d\u0627\u0644\u062a: {mode}\n\u23f0 {ts}",
                    parse_mode="HTML", reply_markup=get_main_keyboard()
                )
            else:
                await message.answer("\u26a0\ufe0f \u062e\u0637\u0627 \u062f\u0631 \u062f\u0631\u06cc\u0627\u0641\u062a \u0648\u0636\u0639\u06cc\u062a", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"\u274c \u062e\u0637\u0627: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("pause"))
async def cmd_pause(message: types.Message):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{_API_BASE}/api/v1/control/pause")
            await message.answer("\u23f8 <b>\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0645\u0648\u0642\u062a\u0627\u064b \u0645\u062a\u0648\u0642\u0641 \u0634\u062f\u0646\u062f</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"\u274c \u062e\u0637\u0627: {str(e)[:100]}", parse_mode="HTML")


@router.message(Command("resume"))
async def cmd_resume(message: types.Message):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{_API_BASE}/api/v1/control/resume")
            await message.answer("\u25b6\ufe0f <b>\u0645\u0639\u0627\u0645\u0644\u0627\u062a \u0627\u0632 \u0633\u0631 \u06af\u0631\u0641\u062a\u0647 \u0634\u062f</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"\u274c \u062e\u0637\u0627: {str(e)[:100]}", parse_mode="HTML")


@router.callback_query(F.data == "cancel")
async def cancel_action(callback: types.CallbackQuery):
    await callback.answer("\u0644\u063a\u0648 \u0634\u062f")
    await callback.message.edit_text("\u274c \u0639\u0645\u0644\u06cc\u0627\u062a \u0644\u063a\u0648 \u0634\u062f.")
