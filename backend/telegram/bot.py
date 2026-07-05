"""
backend/telegram/bot.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram Bot Entry Point (aiogram v3).

Fix applied:
  CB-NEW-4: Added __main__ block so `python -m backend.telegram.bot` works.
            Previously process exited immediately with exit code 0 after import.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from .routers import admin as admin_router
from .handlers import (
    alerts       as alerts_handler,
    control      as control_handler,
    intelligence as intel_handler,
    reports      as reports_handler,
    semi_auto    as semi_auto_handler,
)

logger = logging.getLogger(__name__)

_bot: Optional[Bot]        = None
_dp:  Optional[Dispatcher] = None


def get_bot() -> Bot:
    """Return the active Bot instance. Raises if not initialised."""
    if _bot is None:
        raise RuntimeError("Telegram bot not initialised. Call init_bot() first.")
    return _bot


async def init_bot(token: str) -> tuple[Bot, Dispatcher]:
    """Initialise the bot and dispatcher."""
    global _bot, _dp

    _bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _dp = Dispatcher()

    _dp.include_router(admin_router.router)
    _dp.include_router(control_handler.router)
    _dp.include_router(alerts_handler.router)
    _dp.include_router(reports_handler.router)
    _dp.include_router(semi_auto_handler.router)
    _dp.include_router(intel_handler.router)

    logger.info("[Telegram] bot initialised — 6 routers registered")
    return _bot, _dp


async def start_polling() -> None:
    """Start long-polling (blocks until stopped)."""
    if _bot is None or _dp is None:
        raise RuntimeError("Call init_bot() before start_polling()")
    logger.info("[Telegram] starting long-polling ...")
    await _dp.start_polling(_bot, skip_updates=True)


async def stop_bot() -> None:
    """Gracefully close the bot session."""
    global _bot, _dp
    if _bot:
        await _bot.session.close()
        logger.info("[Telegram] bot session closed")
    _bot = None
    _dp  = None


# CB-NEW-4 FIX: __main__ runner
# `python -m backend.telegram.bot` previously exited immediately
# with code 0 receiving zero Telegram messages.
async def _main() -> None:
    """Standalone runner for Dockerfile.bot."""
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )
    try:
        from backend.core.config import get_settings
        settings = get_settings()
        token = settings.TELEGRAM_BOT_TOKEN
    except Exception as exc:
        logger.critical("[Telegram] Failed to load config: %s", exc)
        raise SystemExit(1) from exc

    if not token:
        logger.critical(
            "[Telegram] TELEGRAM_BOT_TOKEN is not set — set it in your .env file."
        )
        raise SystemExit(1)

    logger.info("[Telegram] initialising bot ...")
    await init_bot(token=token)
    logger.info("[Telegram] starting polling — press Ctrl+C to stop")
    try:
        await start_polling()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Telegram] shutdown signal received")
    finally:
        await stop_bot()
        logger.info("[Telegram] bot stopped cleanly")


if __name__ == "__main__":
    asyncio.run(_main())
