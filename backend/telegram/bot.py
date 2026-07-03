"""
backend/telegram/bot.py
Galaxy Vast AI Trading Platform -- Telegram Bot Entry Point
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")


class TradingBot:
    """Main Telegram bot controller."""

    def __init__(self, token: str = TELEGRAM_TOKEN) -> None:
        self.token = token
        self._app: Optional[object] = None

    async def start(self) -> None:
        """Start the Telegram bot."""
        if not self.token:
            logger.warning("TELEGRAM_BOT_TOKEN not set -- bot disabled")
            return
        logger.info("Starting Telegram bot")
        # Application setup would go here

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        logger.info("Stopping Telegram bot")

    def is_running(self) -> bool:
        return self._app is not None


bot = TradingBot()
