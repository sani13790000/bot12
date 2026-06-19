"""Admin-only commands.

Security:
- Every handler checks data["is_admin"] injected by AuthMiddleware.
- Admin IDs come from TELEGRAM_ADMIN_IDS env variable ONLY.
- No privilege escalation via callback data is possible.
- Broadcast content is length-capped and sent as plain text (no HTML injection).
"""
from __future__ import annotations

import httpx
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)
router = Router(name="admin")

_API_BASE = getattr(settings, "API_BASE_URL", "http://api:8000")
_MAX_BROADCAST_LEN = 4096


def _admin_required(func):
    """Decorator: reject non-admin users."""
    from functools import wraps

    @wraps(func)
    async def wrapper(message: Message, is_admin: bool, **kwargs):
        if not is_admin:
            await message.answer("\u26d4 Admin access required.")
            return
        return await func(message, is_admin=is_admin, **kwargs)

    return wrapper


@router.message(Command("admin"))
@_admin_required
async def cmd_admin_panel(message: Message, **kwargs) -> None:
    """Show admin panel."""
    await message.answer(
        "\U0001f511 *Admin Panel*\n\n"
        "/stats \u2014 Bot & API statistics\n"
        "/broadcast \u003cmsg\u003e \u2014 Send message to all users\n"
        "/health \u2014 Check API health\n"
    )


@router.message(Command("stats"))
@_admin_required
async def cmd_stats(message: Message, **kwargs) -> None:
    """Fetch API stats."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_API_BASE}/health")
        if resp.status_code == 200:
            d = resp.json()
            status = d.get("status", "unknown")
            db = d.get("database", {}).get("connected", False)
            routes = d.get("routes", {}).get("active", "?")
            text = (
                f"\U0001f4ca *API Stats*\n\n"
                f"Status:   `{status}`\n"
                f"DB:       `{'\u2705' if db else '\u274c'}`\n"
                f"Routes:   `{routes}`\n"
            )
            await message.answer(text)
        else:
            await message.answer(f"\u26a0\ufe0f Health check failed: {resp.status_code}")
    except Exception as exc:  # noqa: BLE001
        logger.error("Admin stats error: %s", exc)
        await message.answer("\u274c Failed to fetch stats.")


@router.message(Command("health"))
@_admin_required
async def cmd_health(message: Message, **kwargs) -> None:
    """Quick API health check."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{_API_BASE}/health")
        emoji = "\u2705" if resp.status_code == 200 else "\u274c"
        await message.answer(f"{emoji} API health: `{resp.status_code}`")
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"\u274c API unreachable: {exc}")


@router.message(Command("broadcast"))
@_admin_required
async def cmd_broadcast(message: Message, **kwargs) -> None:
    """
    Broadcast a plain-text message.
    Content is length-capped and logged.
    This is a stub — extend with actual user DB lookup.
    """
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Usage: /broadcast <message>")
        return

    content = parts[1].strip()[:_MAX_BROADCAST_LEN]
    # Log broadcast (sanitised)
    safe = content.replace("\n", " ")[:200]
    logger.info("BROADCAST by uid=%s: %r", message.from_user.id if message.from_user else "?", safe)

    # Stub: send back to admin as confirmation
    await message.answer(
        f"\U0001f4e2 *Broadcast queued:*\n\n{content}\n\n"
        "_(Extend this handler with actual user DB lookup)_"
    )
