"""
backend/telegram/bot.py
Galaxy Vast AI Trading Platform — Telegram Bot Entry Point
"""
from __future__ import annotations
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)
__all__ = ["TelegramBot", "get_bot"]


class TelegramBot:
    """Thin wrapper around python-telegram-bot."""

    def __init__(self, token: Optional[str] = None) -> None:
        self._token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._app: Any = None
        self._started = False

    async def start(self) -> None:
        if not self._token:
            logger.warning("TELEGRAM_BOT_TOKEN not set — bot disabled")
            return
        try:
            from telegram.ext import ApplicationBuilder
            self._app = ApplicationBuilder().token(self._token).build()
            await self._app.initialize()
            self._started = True
            logger.info("Telegram bot started")
        except ImportError:
            logger.warning("python-telegram-bot not installed")
        except Exception as exc:
            logger.error("Telegram bot start failed: %s", exc)

    async def send_message(self, chat_id: str, text: str) -> bool:
        if not self._app or not self._started:
            logger.debug("Bot not started — skipping message to %s", chat_id)
            return False
        try:
            await self._app.bot.send_message(chat_id=chat_id, text=text)
            return True
        except Exception as exc:
            logger.error("send_message failed: %s", exc)
            return False

    async def stop(self) -> None:
        if self._app and self._started:
            await self._app.shutdown()
            self._started = False


_bot: Optional[TelegramBot] = None

def get_bot() -> TelegramBot:
    global _bot
    if _bot is None:
        _bot = TelegramBot()
    return _bot
