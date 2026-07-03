"""
backend/telegram/handlers/control.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram command handlers for bot and trading control.

Commands
--------
/start      — welcome message
/status     — system health summary
/pause      — pause automated trading
/resume     — resume automated trading
/kill       — emergency kill-switch (requires confirmation)
/positions  — list open positions
/close <ticket> — close a specific position
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "🚀 *Galaxy Vast AI Trading Bot*\n\n"
    "🔹 `/status`   — وضعیت سیستم\n"
    "🔹 `/pause`    — توقف معاملات خودکار\n"
    "🔹 `/resume`   — ادامه معاملات\n"
    "🔹 `/kill`     — اضطراری kill-switch\n"
    "🔹 `/positions`— پوزیشن‌های باز\n"
    "🔹 `/alerts`   — هشدارهای اخیر\n"
)


async def cmd_start(update: object, context: object) -> None:
    """Send the welcome message with the command list."""
    try:
        await update.message.reply_text(WELCOME_TEXT, parse_mode="Markdown")  # type: ignore
    except Exception as exc:
        logger.exception("[control] cmd_start: %s", exc)


async def cmd_status(update: object, context: object) -> None:
    """Report system health: kill-switch state, open positions, scheduler."""
    try:
        from telegram import Update
        upd: Update = update  # type: ignore

        lines = ["📊 *System Status*\n"]

        # Kill-switch
        try:
            from backend.risk.kill_switch import kill_switch
            ks_state = "🟢 ACTIVE" if kill_switch.is_active() else "🔴 INACTIVE"
            lines.append(f"🛡️ Kill-Switch: `{ks_state}`")
        except Exception:
            lines.append("🛡️ Kill-Switch: `unknown`")

        # Open positions
        try:
            from backend.execution.order_state_machine import order_state_machine
            active = order_state_machine.active_tickets()
            lines.append(f"📈 Open Positions: `{len(active)}`")
        except Exception:
            lines.append("📈 Open Positions: `unknown`")

        # Scheduler
        try:
            from backend.services.scheduler import scheduler
            task_count = len(scheduler._tasks)  # noqa: SLF001
            lines.append(f"⏰ Scheduler Tasks: `{task_count}`")
        except Exception:
            lines.append("⏰ Scheduler: `unknown`")

        await upd.message.reply_text("\n".join(lines), parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[control] cmd_status: %s", exc)
        try:
            await update.message.reply_text(f"❌ خطا: {exc}")  # type: ignore
        except Exception:
            pass


async def cmd_pause(update: object, context: object) -> None:
    """Pause automated trading by activating the kill-switch."""
    try:
        from backend.risk.kill_switch import kill_switch
        kill_switch.activate(reason="Telegram /pause")
        await update.message.reply_text(  # type: ignore
            "⏸️ معاملات خودکار *متوقف* شد.\n"
            "برای ادامه `/resume` بزنید.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[control] cmd_pause: %s", exc)
        await update.message.reply_text(f"❌ {exc}")  # type: ignore


async def cmd_resume(update: object, context: object) -> None:
    """Resume automated trading by deactivating the kill-switch."""
    try:
        from backend.risk.kill_switch import kill_switch
        kill_switch.deactivate()
        await update.message.reply_text(  # type: ignore
            "▶️ معاملات خودکار *از سر گرفته شد*.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[control] cmd_resume: %s", exc)
        await update.message.reply_text(f"❌ {exc}")  # type: ignore


async def cmd_kill(update: object, context: object) -> None:
    """
    Emergency kill-switch.  Requires the word 'CONFIRM' as an argument::

        /kill CONFIRM
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args = ctx.args or []
        if not args or args[0].upper() != "CONFIRM":
            await upd.message.reply_text(
                "⚠️ برای فعال‌کردن kill-switch بنویسید:\n`/kill CONFIRM`",
                parse_mode="Markdown",
            )
            return

        from backend.risk.kill_switch import kill_switch
        kill_switch.activate(reason="Telegram /kill CONFIRM")
        await upd.message.reply_text(
            "🚨 *KILL-SWITCH فعال شد*\n"
            "تمام معاملات جدید متوقف شد.",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.exception("[control] cmd_kill: %s", exc)
        try:
            await update.message.reply_text(f"❌ {exc}")  # type: ignore
        except Exception:
            pass


async def cmd_positions(update: object, context: object) -> None:
    """List all active trade positions."""
    try:
        from backend.execution.order_state_machine import order_state_machine
        tickets = order_state_machine.active_tickets()

        if not tickets:
            await update.message.reply_text("✅ هیچ پوزیشن بازی وجود ندارد.")  # type: ignore
            return

        lines = [f"📈 *پوزیشن‌های باز* ({len(tickets)})", ""]
        for t in tickets[:20]:
            state = order_state_machine.get_state(t)
            lines.append(f"• Ticket `{t}` — `{state}`")

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")  # type: ignore

    except Exception as exc:
        logger.exception("[control] cmd_positions: %s", exc)
        await update.message.reply_text(f"❌ {exc}")  # type: ignore


async def cmd_close(update: object, context: object) -> None:
    """
    /close <ticket>

    Close a specific open position by ticket number.
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args = ctx.args or []
        if not args or not args[0].isdigit():
            await upd.message.reply_text(
                "⚠️ استفاده: `/close <ticket>`",
                parse_mode="Markdown",
            )
            return

        ticket = int(args[0])
        from backend.execution.execution_service import execution_service
        result = await execution_service.close(ticket)

        if result.success:
            await upd.message.reply_text(
                f"✅ پوزیشن `{ticket}` بسته شد.",
                parse_mode="Markdown",
            )
        else:
            await upd.message.reply_text(
                f"❌ بستن پوزیشن `{ticket}` شکست خورد: {result.error}",
                parse_mode="Markdown",
            )

    except Exception as exc:
        logger.exception("[control] cmd_close: %s", exc)
        try:
            await update.message.reply_text(f"❌ {exc}")  # type: ignore
        except Exception:
            pass
