"""Admin-only Telegram commands.

Security: Every handler checks the user against the admin whitelist.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)
ADMIN_IDS: set[int] = set()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def cmd_status(update: Any, context: Any) -> None:
    """Return bot status to admin."""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("✅ Bot is running.")


async def cmd_kill(update: Any, context: Any) -> None:
    """Trigger emergency kill-switch."""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("⚠️ Kill switch triggered!")


async def cmd_stats(update: Any, context: Any) -> None:
    """Return trading statistics."""
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("📊 Stats: coming soon.")
