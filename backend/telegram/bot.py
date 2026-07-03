"""
backend/telegram/bot.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram Bot Entry Point (aiogram v3).

Initialises the Aiogram Bot and Dispatcher, registers all routers,
and provides start/stop lifecycle hooks for FastAPI.

Usage (from FastAPI lifespan)
-----------------------------
    from backend.telegram.bot import init_bot, start_polling, stop_bot

    bot, dp = await init_bot(token=settings.TELEGRAM_TOKEN)
    asyncio.create_task(start_polling())   # non-blocking
    # ... on shutdown:
    await stop_bot()
"""
from __future__ import annotations

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


# ── Public helpers ──────────────────────────────────────────────────── #

def get_bot() -> Bot:
    """Return the active Bot instance. Raises if not initialised."""
    if _bot is None:
        raise RuntimeError(
            "Telegram bot not initialised. Call init_bot() first."
        )
    return _bot


async def init_bot(token: str) -> tuple[Bot, Dispatcher]:
    """
    Initialise the bot and dispatcher.

    Call this once at application startup.  All routers are
    registered in dependency order so commands don't shadow each other.
    """
    global _bot, _dp  # noqa: PLW0603

    _bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher()

    # ── Register routers (order matters for command priority) ── #
    _dp.include_router(admin_router.router)          # admin-only
    _dp.include_router(control_handler.router)       # /start /status /pause …
    _dp.include_router(alerts_handler.router)        # /alerts /setalerts
    _dp.include_router(reports_handler.router)       # /report
    _dp.include_router(semi_auto_handler.router)     # /semiauto /pending
    _dp.include_router(intel_handler.router)         # /analyse /signal /bias /intel

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
    global _bot, _dp  # noqa: PLW0603
    if _bot:
        await _bot.session.close()
        logger.info("[Telegram] bot session closed")
    _bot = None
    _dp  = None
