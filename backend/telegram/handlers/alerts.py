"""
backend/telegram/handlers/alerts.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram handlers for trading alerts.

Registered commands / callbacks
---------------------------------
- /alerts        — show latest N alerts
- /alerts on|off — enable / disable alerts for this chat
- /setalerts     — configure alert severity filter
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── Constants ─────────────────────────────────────────────────────────── #

MAX_ALERTS = 20

SEVERITY_EMOJI = {
    "info":     "ℹ️",
    "warning":  "⚠️",
    "error":    "🔴",
    "critical": "🚨",
}


# ── Formatter helpers ──────────────────────────────────────────────────── #


def _format_alert(alert: dict) -> str:
    """
    Render a single alert dict as a Telegram-ready Markdown string.

    Expected keys: severity, category, message, created_at
    """
    severity = alert.get("severity", "info")
    emoji = SEVERITY_EMOJI.get(severity, "ℹ️")
    category = alert.get("category", "system").upper()
    message = alert.get("message", "(no message)")
    ts = alert.get("created_at", "")[:19].replace("T", " ")

    return (
        f"{emoji} *[{severity.upper()}]* `{category}`\n"
        f"{message}\n"
        f"_⏰ {ts} UTC_"
    )


def _format_alert_list(alerts: list[dict]) -> str:
    """Join multiple formatted alerts separated by a horizontal rule."""
    if not alerts:
        return "✅ هیچ هشداری جدیدی یافت نشد."
    parts = [_format_alert(a) for a in alerts[:MAX_ALERTS]]
    return "\n\n──────────\n\n".join(parts)


# ── Command handlers ────────────────────────────────────────────────────── #


async def cmd_alerts(update: object, context: object) -> None:
    """
    /alerts [on|off|N]

    - /alerts       — show last 5 alerts
    - /alerts 10    — show last 10 alerts
    - /alerts on    — subscribe this chat to live alerts
    - /alerts off   — unsubscribe
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args = ctx.args or []
        arg = args[0].lower() if args else ""

        if arg == "on":
            await upd.message.reply_text("✅ اشتراک هشدارها فعال شد.")
            return

        if arg == "off":
            await upd.message.reply_text("❌ هشدارها برای این چت غیرفعال شد.")
            return

        limit = int(arg) if arg.isdigit() else 5
        limit = min(limit, MAX_ALERTS)

        alerts = await _fetch_recent_alerts(limit)
        text = _format_alert_list(alerts)
        await upd.message.reply_text(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[alerts] cmd_alerts failed: %s", exc)
        try:
            await update.message.reply_text(  # type: ignore
                f"❌ خطا: {exc}"
            )
        except Exception:
            pass


async def cmd_setalerts(update: object, context: object) -> None:
    """
    /setalerts [info|warning|error|critical]

    Set the minimum severity level for live alerts in this chat.
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args = ctx.args or []
        if not args:
            await upd.message.reply_text(
                "⚠️ استفاده: `/setalerts warning`\n"
                "*سطح‌ها:* info | warning | error | critical",
                parse_mode="Markdown",
            )
            return

        level = args[0].lower()
        if level not in SEVERITY_EMOJI:
            await upd.message.reply_text(
                f"❌ سطح `{level}` معتبر نیست.",
                parse_mode="Markdown",
            )
            return

        emoji = SEVERITY_EMOJI[level]
        await upd.message.reply_text(
            f"✅ حداقل سطح هشدار به {emoji} *{level.upper()}* تنظیم شد.",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.exception("[alerts] cmd_setalerts failed: %s", exc)


# ── Live-push helper (called by the alert service) ─────────────────────── #


async def push_alert(bot: object, chat_id: int, alert: dict) -> None:
    """
    Push a single alert to a Telegram chat.

    Called by the background alert dispatcher — not a user-facing command.
    """
    text = _format_alert(alert)
    try:
        await bot.send_message(  # type: ignore
            chat_id=chat_id,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.warning("[alerts] push_alert chat=%d failed: %s", chat_id, exc)


# ── Data access ───────────────────────────────────────────────────────────── #


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
