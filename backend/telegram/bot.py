"""
backend/telegram/bot.py
Galaxy Vast AI — Telegram Bot Entry Point

Initializes the aiogram bot instance and dispatches to handlers.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_bot: Optional[object] = None
_dp: Optional[object] = None


def get_bot():
    """Return the global bot instance."""
    global _bot
    if _bot is None and _TOKEN:
        try:
            from aiogram import Bot
            _bot = Bot(token=_TOKEN, parse_mode="HTML")
        except ImportError:
            logger.warning("aiogram not installed; Telegram bot disabled")
    return _bot


def get_dispatcher():
    """Return the global dispatcher instance."""
    global _dp
    if _dp is None:
        try:
            from aiogram import Dispatcher
            _dp = Dispatcher()
        except ImportError:
            logger.warning("aiogram not installed; dispatcher disabled")
    return _dp


async def start_bot() -> None:
    """Start the Telegram bot polling loop."""
    bot = get_bot()
    dp = get_dispatcher()
    if not bot or not dp:
        logger.warning("Telegram bot not configured (TELEGRAM_BOT_TOKEN missing or aiogram not installed)")
        return
    logger.info("Starting Telegram bot polling...")
    try:
        await dp.start_polling(bot)
    except Exception as exc:
        logger.error("Telegram bot error: %s", exc)


async def stop_bot() -> None:
    """Stop the Telegram bot."""
    bot = get_bot()
    if bot:
        try:
            await bot.session.close()
        except Exception:
            pass
