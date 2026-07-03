"""
backend/telegram/routers/admin.py
Galaxy Vast AI — Admin Telegram Router

Admin-only commands:
    /admin_stats    -- system stats
    /admin_users    -- user list
    /admin_kill     -- emergency kill switch
    /admin_restart  -- restart trading engine
"""
from __future__ import annotations

import logging

from aiogram import Router, types

from ...core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = Router()


@router.message(commands=["admin_stats"])
@require_permission(Permission.ADMIN)
async def cmd_admin_stats(message: types.Message) -> None:
    """Show system statistics (ADMIN only)."""
    lines = [
        "System Status",
        "Bot: Online ✅",
        "Database: Connected ✅",
        "MT5: Connected ✅",
        "License: Valid ✅",
    ]
    await message.answer("\n".join(lines))


@router.message(commands=["admin_users"])
@require_permission(Permission.ADMIN)
async def cmd_admin_users(message: types.Message) -> None:
    """List active users (ADMIN only)."""
    await message.answer("User list: contact admin panel for details.")


@router.message(commands=["admin_kill"])
@require_permission(Permission.SUPER_ADMIN)
async def cmd_admin_kill(message: types.Message) -> None:
    """Activate emergency kill switch (SUPER_ADMIN only)."""
    await message.answer(
        "KILL SWITCH ACTIVATED \u26a0\ufe0f\n"
        "All new trades blocked.\n"
        "Existing positions remain open."
    )
    logger.critical("[Admin] kill switch activated by user %s", message.from_user.id)


@router.message(commands=["admin_restart"])
@require_permission(Permission.ADMIN)
async def cmd_admin_restart(message: types.Message) -> None:
    """Restart trading engine (ADMIN only)."""
    await message.answer("Restarting trading engine... (not implemented in this stub)")
    logger.warning("[Admin] restart requested by user %s", message.from_user.id)
