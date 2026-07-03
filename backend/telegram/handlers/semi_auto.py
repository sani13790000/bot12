"""
backend/telegram/handlers/semi_auto.py
Semi-Auto Trading Telegram Handler
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_pending_signals(update: Any, context: Any) -> None:
    """Show pending signals awaiting approval."""
    await update.message.reply_text("Pending Signals:\nNo signals pending approval.")


async def handle_approve(update: Any, context: Any) -> None:
    """Approve a pending signal."""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /approve <signal_id>")
        return
    await update.message.reply_text(f"Signal {args[0]} approved.")


async def handle_reject(update: Any, context: Any) -> None:
    """Reject a pending signal."""
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /reject <signal_id>")
        return
    await update.message.reply_text(f"Signal {args[0]} rejected.")


async def handle_semi_auto_status(update: Any, context: Any) -> None:
    """Show semi-auto mode status."""
    await update.message.reply_text("✅ Semi-auto mode is active.")
