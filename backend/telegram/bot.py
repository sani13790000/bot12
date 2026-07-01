"""
backend/telegram/bot.py
Galaxy Vast AI Trading Platform — Telegram Bot Entry Point
"""
from __future__ import annotations

import logging
import os

_LOG = logging.getLogger(__name__)

_bot_instance = None
_dp_instance = None


def get_bot():
    global _bot_instance
    if _bot_instance is None:
        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode
            token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
            if not token:
                raise RuntimeError('TELEGRAM_BOT_TOKEN not set')
            _bot_instance = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        except ImportError:
            _LOG.warning('aiogram not installed')
    return _bot_instance


def get_dispatcher():
    global _dp_instance
    if _dp_instance is None:
        try:
            from aiogram import Dispatcher
            _dp_instance = Dispatcher()
        except ImportError:
            _LOG.warning('aiogram not installed')
    return _dp_instance


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    bot = get_bot()
    dp = get_dispatcher()
    if bot and dp:
        await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
