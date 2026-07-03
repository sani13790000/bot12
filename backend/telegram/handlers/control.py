"""
backend/telegram/handlers/control.py
Telegram control handler -- start/stop/status commands.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_start(update: Any, context: Any) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to Galaxy Vast AI Trading Bot!\n"
        "Use /help for available commands."
    )


async def handle_stop(update: Any, context: Any) -> None:
    """Handle /stop command."""
    await update.message.reply_text("Bot stopped. Use /start to resume.")


async def handle_status(update: Any, context: Any) -> None:
    """Handle /status command."""
    await update.message.reply_text("✅ Bot is active and monitoring markets.")


async def handle_help(update: Any, context: Any) -> None:
    """Handle /help command."""
    help_text = (
        "/start - Start the bot\n"
        "/stop - Stop the bot\n"
        "/status - Check bot status\n"
        "/trades - View open trades\n"
        "/balance - Check account balance\n"
        "/help - Show this message"
    )
    await update.message.reply_text(help_text)
