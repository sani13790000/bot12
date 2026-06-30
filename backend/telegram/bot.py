"""
backend/telegram/bot.py
Galaxy Vast AI — Telegram Bot Gateway

Responsibilities:
- Initialize aiogram Bot + Dispatcher.
- Register routers from backend.telegram.handlers.*.
- Provide safe startup / shutdown lifecycle.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode

from backend.telegram.handlers import alerts, control, intelligence, reports, semi_auto
from backend.core.logger import get_logger

_LOGGER = get_logger(__name__)


class TelegramBotService:
    """Lifecycle manager for the Telegram bot."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.bot: Optional[Bot] = None
        self.dispatcher: Optional[Dispatcher] = None

    async def start(self) -> None:
        if not self.token:
            _LOGGER.warning("TELEGRAM_BOT_TOKEN not set; Telegram bot disabled.")
            return
        self.bot = Bot(token=self.token, parse_mode=ParseMode.HTML)
        self.dispatcher = Dispatcher()
        self._register_routers()
        _LOGGER.info("Telegram bot starting polling...")
        await self.dispatcher.start_polling(self.bot)

    async def stop(self) -> None:
        if self.bot:
            await self.bot.session.close()
            _LOGGER.info("Telegram bot session closed.")

    def _register_routers(self) -> None:
        self.dispatcher.include_router(control.router)
        self.dispatcher.include_router(semi_auto.router)
        self.dispatcher.include_router(intelligence.router)
        self.dispatcher.include_router(reports.router)
        self.dispatcher.include_router(alerts.router)


# Global singleton for dependency injection
_bot_service: Optional[TelegramBotService] = None


async def start_telegram_bot(token: Optional[str] = None) -> TelegramBotService:
    global _bot_service
    _bot_service = TelegramBotService(token=token)
    asyncio.create_task(_bot_service.start())
    return _bot_service


def get_bot_service() -> Optional[TelegramBotService]:
    return _bot_service
