"""
backend/telegram/bot.py
Galaxy Vast AI — Telegram Bot Entry Point

Initialises the Aiogram Bot and Dispatcher, registers all routers,
and provides start/stop lifecycle hooks for FastAPI.
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from .routers import admin as admin_router
from .handlers import (
    alerts     as alerts_handler,
    control    as control_handler,
    reports    as reports_handler,
    semi_auto  as semi_auto_handler,
    intelligence as intel_handler,
)

logger = logging.getLogger(__name__)

_bot: Optional[Bot] = None
_dp:  Optional[Dispatcher] = None


def get_bot() -> Bot:
    if _bot is None:
        raise RuntimeError("Telegram bot not initialised. Call init_bot() first.")
    return _bot


async def init_bot(token: str) -> tuple[Bot, Dispatcher]:
    """
    Initialise the bot and dispatcher.
    Call this once at application startup.
    """
    global _bot, _dp

    _bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    _dp = Dispatcher()

    # Register routers
    _dp.include_router(admin_router.router)
    _dp.include_router(control_handler.router)
    _dp.include_router(reports_handler.router)
    _dp.include_router(alerts_handler.router)
    _dp.include_router(semi_auto_handler.router)
    _dp.include_router(intel_handler.router)

    logger.info("[Telegram] bot initialised")
    return _bot, _dp


async def start_polling() -> None:
    """Start long-polling (blocks until stopped)."""
    if _bot is None or _dp is None:
        raise RuntimeError("Call init_bot() before start_polling()")
    logger.info("[Telegram] starting polling...")
    await _dp.start_polling(_bot, skip_updates=True)


async def stop_bot() -> None:
    """Gracefully close the bot session."""
    global _bot, _dp
    if _bot:
        await _bot.session.close()
        logger.info("[Telegram] bot session closed")
    _bot = None
    _dp  = None
