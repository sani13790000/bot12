"""
backend/telegram/routers/admin.py
Galaxy Vast AI — Admin-only Telegram commands

Security:
- Every handler checks data["is_admin"] injected by AuthMiddleware.
- Admin IDs come from TELEGRAM_ADMIN_IDS env variable ONLY.
- No privilege escalation via callback data.

NOTE: Restored from corrupted source. f-string backslash violations fixed.
"""
from __future__ import annotations
import logging
import os
from typing import Any, Set
logger = logging.getLogger(__name__)

_ADMIN_IDS: Set[int] = {
    int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS", "").split(",") if x.strip().isdigit()
}


def is_admin(user_id: int) -> bool:
    return user_id in _ADMIN_IDS


async def cmd_admin_stats(message: Any, stats: dict) -> None:
    """Admin: show system statistics."""
    if not is_admin(message.from_user.id):
        await message.answer("\u274c Access denied")
        return
    lines = ["\U0001f511 <b>Admin Stats</b>\n"]
    for k, v in stats.items():
        lines.append(f"  {k}: {v}")
    try:
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        logger.error("cmd_admin_stats error: %s", exc)


async def cmd_kill_switch(message: Any, engine: Any) -> None:
    """Admin: activate kill switch."""
    if not is_admin(message.from_user.id):
        await message.answer("\u274c Access denied")
        return
    await engine.activate_kill_switch(admin_id=str(message.from_user.id), reason="manual")
    await message.answer("\U0001f6a8 <b>Kill switch activated</b>", parse_mode="HTML")
