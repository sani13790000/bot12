"""
backend/telegram/routers/admin.py
Admin-only Telegram commands.

Security:
- Every handler checks data["is_admin"] injected by AuthMiddleware.
- Admin IDs come from TELEGRAM_ADMIN_IDS env variable ONLY.
- No privilege escalation via callback data is possible.
"""
from __future__ import annotations

import httpx
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Show API health and statistics."""
    data = message.bot.get("user_data", {})
    if not data.get("is_admin"):
        await message.answer("Access denied.")
        return
    try:
        from backend.core.config import get_settings
        settings  = get_settings()
        api_base  = getattr(settings, "API_BASE_URL", "http://localhost:8000")
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{api_base}/health")
        if resp.status_code == 200:
            health = resp.json()
            status = health.get("status", "unknown")
            db     = health.get("db", False)
            routes = health.get("routes", 0)
            db_icon = chr(0x2705) if db else chr(0x274c)
            text = (
                "📊 *API Stats*\n\n"
                f"Status:   `{status}`\n"
                f"DB:       `{db_icon}`\n"
                f"Routes:   `{routes}`\n"
            )
            await message.answer(text)
        else:
            await message.answer(f"Health check failed: {resp.status_code}")
    except Exception as exc:
        logger.error("Admin stats error: %s", exc)
        await message.answer("Failed to fetch stats.")


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message) -> None:
    """Broadcast a message to all subscribers (admin only)."""
    data = message.bot.get("user_data", {})
    if not data.get("is_admin"):
        await message.answer("Access denied.")
        return
    text_parts = message.text.split(" ", 1)
    if len(text_parts) < 2 or not text_parts[1].strip():
        await message.answer("Usage: /broadcast <message>")
        return
    broadcast_text = text_parts[1].strip()[:1000]  # length cap
    try:
        from backend.services.user_service import UserService
        svc   = UserService()
        users = await svc.get_all_subscriber_ids()
        sent  = 0
        for uid in users:
            try:
                await message.bot.send_message(uid, broadcast_text)
                sent += 1
            except Exception:
                pass
        await message.answer(f"Broadcast sent to {sent}/{len(users)} users.")
    except Exception as exc:
        logger.error("Broadcast error: %s", exc)
        await message.answer("Broadcast failed.")
