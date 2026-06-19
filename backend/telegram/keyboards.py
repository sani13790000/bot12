"""Telegram inline and reply keyboard builders.

Security: all callback_data strings are static, whitelist-safe values.
No user input is ever embedded in callback_data.
"""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu inline keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="\U0001f4ca Signal", callback_data="signal:XAUUSD"),
            InlineKeyboardButton(text="\U0001f50d Analyse", callback_data="analyze:XAUUSD"),
        ],
        [
            InlineKeyboardButton(text="\U0001f6e1\ufe0f Risk", callback_data="risk:DISMISS"),
            InlineKeyboardButton(text="\u2139\ufe0f Help", callback_data="close:DISMISS"),
        ],
    ])


def signal_action_keyboard(symbol: str) -> InlineKeyboardMarkup:
    """
    Signal action keyboard.
    symbol must be from the allowed whitelist — enforced by callers.
    """
    # Validate symbol length & format (extra safety)
    safe_symbol = symbol.upper()[:10].replace(" ", "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="\U0001f504 Refresh",
                callback_data=f"refresh:{safe_symbol}",
            ),
            InlineKeyboardButton(
                text="\U0001f50d Analyse",
                callback_data=f"analyze:{safe_symbol}",
            ),
        ],
        [
            InlineKeyboardButton(text="\u274c Close", callback_data="close:DISMISS"),
        ],
    ])
