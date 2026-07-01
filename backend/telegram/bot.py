"""
backend/telegram/bot.py
Galaxy Vast AI Trading Platform — Telegram Bot Entry Point
"""
from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)


def get_bot_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")
    return token


try:
    from aiogram import Bot, Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    _token = os.environ.get("TELEGRAM_BOT_TOKEN", "placeholder")
    bot = Bot(token=_token) if _token and _token != "placeholder" else None
    dp = Dispatcher(storage=MemoryStorage()) if bot else None
except ImportError:
    _LOG.debug("aiogram not installed - Telegram bot disabled")
    bot = None
    dp = None


async def start_bot() -> None:
    if bot is None or dp is None:
        _LOG.warning("Telegram bot not configured - skipping startup")
        return
    _LOG.info("Starting Telegram bot...")
    await dp.start_polling(bot)


async def stop_bot() -> None:
    if bot is not None:
        await bot.session.close()
