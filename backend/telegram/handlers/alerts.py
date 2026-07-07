"""
backend/telegram/handlers/alerts.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram handlers for trading alerts.

Registered commands
-------------------
- /alerts        – show latest N alerts
- /alerts on|off – enable / disable alerts for this chat
- /setalerts     – configure alert severity filter
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()

MAX_ALERTS = 20

SEVERITY_EMOJI: dict[str, str] = {
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🔥",
    "critical": "😨",
}


# ── Formatter helpers ────────────────────────────────────────────── #


def _format_alert(alert: dict) -> str:
    """Render a single alert dict as Telegram Markdown."""
    severity = alert.get("severity", "info")
    emoji = SEVERITY_EMOJI.get(severity, "ℹ️")
    category = alert.get("category", "system").upper()
    message = alert.get("message", "(no message)")
    ts = alert.get("created_at", "")[:19].replace("T", " ")
    return f"{emoji} *[{severity.upper()}]* `{category}`\n{message}\n_🕐 {ts} UTC_"


def _format_alert_list(alerts: list[dict]) -> str:
    """Join multiple formatted alerts separated by a horizontal rule."""
    if not alerts:
        return "✅ هیچ هشدار جدیدی یافت نشد."
    parts = [_format_alert(a) for a in alerts[:MAX_ALERTS]]
    return "\n\n──────────\n\n".join(parts)


# ── Command handlers ─────────────────────────────────────────────── #


@router.message(Command("alerts"))
async def cmd_alerts(message: types.Message) -> None:
    """
    /alerts [on|off|N]

    - /alerts        – show last 5 alerts
    - /alerts 10     – show last 10 alerts
    - /alerts on     – subscribe this chat to live alerts
    - /alerts off    – unsubscribe
    """
    try:
        args = (message.text or "").split()[1:]
        arg = args[0].lower() if args else ""

        if arg == "on":
            await message.answer("✅ اشتراک هشدارهای زنده فعال شد.")
            return

        if arg == "off":
            await message.answer("❌ هشدارهای زنده برای این چت غیرفعال شد.")
            return

        limit = int(arg) if arg.isdigit() else 5
        limit = min(limit, MAX_ALERTS)

        alerts = await _fetch_recent_alerts(limit)
        text = _format_alert_list(alerts)
        await message.answer(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[alerts] cmd_alerts failed: %s", exc)
        try:
            await message.answer(f"❌ خطا: {exc}")
        except Exception:
            pass


@router.message(Command("setalerts"))
async def cmd_setalerts(message: types.Message) -> None:
    """
    /setalerts [info|warning|error|critical]

    Set the minimum severity level for live alerts in this chat.
    """
    try:
        args = (message.text or "").split()[1:]
        if not args:
            await message.answer(
                "⚠️ استفاده: `/setalerts warning`\n*سطح‌ها:* info | warning | error | critical",
                parse_mode="Markdown",
            )
            return

        level = args[0].lower()
        if level not in SEVERITY_EMOJI:
            await message.answer(
                f"❌ سطح `{level}` معتبر نیست.",
                parse_mode="Markdown",
            )
            return

        emoji = SEVERITY_EMOJI[level]
        await message.answer(
            f"✅ حداقل سطح هشدار به {emoji} *{level.upper()}* تنظیم شد.",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.exception("[alerts] cmd_setalerts failed: %s", exc)


# ── Live-push helper (called by the alert service) ─────────────── #


async def push_alert(bot: object, chat_id: int, alert: dict) -> None:
    """Push a single alert to a Telegram chat."""
    text = _format_alert(alert)
    try:
        await bot.send_message(  # type: ignore[attr-defined]
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning("[alerts] push_alert chat=%d failed: %s", chat_id, exc)


# ── Data access ──────────────────────────────────────────────────── #


async def _fetch_recent_alerts(limit: int = 5) -> list[dict]:
    """Fetch recent alerts from the database (best-effort)."""
    try:
        from backend.database.client import db_client

        rows = await db_client.select(
            "alerts",
            limit=limit,
            order="created_at.desc",
        )
        return rows or []
    except Exception as exc:
        logger.warning("[alerts] _fetch_recent_alerts failed: %s", exc)
        return []
