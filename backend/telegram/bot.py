"""Galaxy Vast AI Trading Platform
Telegram Bot — Entry Point

Runs as: python -m backend.telegram.bot
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from backend.core.config import settings
from backend.telegram.middlewares import AuthMiddleware, RateLimitMiddleware, LoggingMiddleware
from backend.telegram.routers import register_all_routers
from backend.core.logger import get_logger

logger = get_logger(__name__)


async def on_startup(bot: Bot) -> None:
    """Called once when bot starts — sets webhook or logs polling mode."""
    me = await bot.get_me()
    logger.info(
        "Bot started | id=%d | username=@%s | mode=polling",
        me.id, me.username,
    )
    # Notify admin on startup
    admin_id = getattr(settings, "TELEGRAM_ADMIN_ID", None)
    if admin_id:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text=(
                    "\u2705 *Galaxy Vast Bot started*\n"
                    f"Version: `2.0.0`\n"
                    f"Environment: `{settings.ENVIRONMENT}`"
                ),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not send startup message to admin: %s", exc)


async def on_shutdown(bot: Bot) -> None:
    """Called on graceful shutdown."""
    logger.info("Bot shutting down...")
    admin_id = getattr(settings, "TELEGRAM_ADMIN_ID", None)
    if admin_id:
        try:
            await bot.send_message(
                chat_id=int(admin_id),
                text="\u26d4 *Galaxy Vast Bot stopped*",
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:  # noqa: BLE001
            pass
    await bot.session.close()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.critical("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # --- Middleware stack (order matters: outer → inner) ---
    dp.message.middleware(LoggingMiddleware())
    dp.message.middleware(RateLimitMiddleware())
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(LoggingMiddleware())
    dp.callback_query.middleware(RateLimitMiddleware())
    dp.callback_query.middleware(AuthMiddleware())

    # --- Register all routers ---
    register_all_routers(dp)

    # --- Lifecycle hooks ---
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("Starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
