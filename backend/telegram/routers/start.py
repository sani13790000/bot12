"""Start / Welcome handler."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from backend.telegram.keyboards import main_menu_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, is_admin: bool, **kwargs) -> None:
    """Handle /start command."""
    user = message.from_user
    name = user.first_name if user else "Trader"

    admin_note = "\n\n\U0001f511 *Admin mode active*" if is_admin else ""

    text = (
        f"\U0001f30c Welcome to *Galaxy Vast AI Trading Bot*, {name}!\n\n"
        "\U0001f4ca Real-time signals powered by SMC + AI\n"
        "\U0001f6e1\ufe0f Multi-layer risk management\n"
        "\U0001f9e0 7-agent voting system\n"
        f"{admin_note}\n\n"
        "Use /help to see available commands."
    )
    await message.answer(text, reply_markup=main_menu_keyboard())
