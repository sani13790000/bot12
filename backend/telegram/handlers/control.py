"""
backend/telegram/handlers/control.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram command handlers for bot and trading control.

Commands
--------
/start       – welcome message
/status      – system health summary
/pause       – pause automated trading
/resume      – resume automated trading
/kill        – emergency kill-switch (requires confirmation)
/positions   – list open positions
/close <ticket> – close a specific position
"""

from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "🚀 *Galaxy Vast AI Trading Bot*\n\n"
    "🔹 `/status`    – وضعیت سیستم\n"
    "🔹 `/pause`     – توقف معاملات خودکار\n"
    "🔹 `/resume`    – ادامه معاملات\n"
    "🔹 `/kill`      – اضطراری kill-switch\n"
    "🔹 `/positions` – پوزیشن‌های باز\n"
    "🔹 `/alerts`    – هشدارهای اخیر\n"
)


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """Send the welcome message with the command list."""
    try:
        await message.answer(WELCOME_TEXT, parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[control] cmd_start: %s", exc)


@router.message(Command("status"))
async def cmd_status(message: types.Message) -> None:
    """Report system health: kill-switch state, open positions, scheduler, license."""
    try:
        lines = ["📊 *System Status*\n"]

        # Kill-switch
        try:
            from backend.risk.kill_switch import kill_switch

            ks_state = "🐂 ACTIVE" if kill_switch.is_active() else "🔴 INACTIVE"
            lines.append(f"🛑️ Kill-Switch: `{ks_state}`")
        except Exception:
            lines.append("🛑️ Kill-Switch: `unknown`")

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

        # License
        try:
            from backend.license.engine import license_engine

            valid = license_engine.is_valid()
            lines.append(f"🔑 License: `{'Valid ✅' if valid else 'INVALID ❌'}`")
        except Exception:
            lines.append("🔑 License: `unknown`")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[control] cmd_status: %s", exc)
        try:
            await message.answer(f"❌ خطا: {exc}")
        except Exception:
            pass


@router.message(Command("pause"))
async def cmd_pause(message: types.Message) -> None:
    """Pause automated trading by activating the kill-switch."""
    try:
        from backend.risk.kill_switch import kill_switch

        kill_switch.activate(reason="Telegram /pause")
        await message.answer(
            "⏸️ معاملات خودکار *متوقف* شد.\nبرای ادامه `/resume` بزنید.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[control] cmd_pause: %s", exc)
        await message.answer(f"❌ {exc}")


@router.message(Command("resume"))
async def cmd_resume(message: types.Message) -> None:
    """Resume automated trading by deactivating the kill-switch."""
    try:
        from backend.risk.kill_switch import kill_switch

        kill_switch.deactivate()
        await message.answer(
            "▶️ معاملات خودکار *از سر گرفته شد*.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[control] cmd_resume: %s", exc)
        await message.answer(f"❌ {exc}")


@router.message(Command("kill"))
async def cmd_kill(message: types.Message) -> None:
    """
    Emergency kill-switch. Requires the word 'CONFIRM' as argument:
        /kill CONFIRM
    """
    try:
        args = (message.text or "").split()[1:]
        if not args or args[0].upper() != "CONFIRM":
            await message.answer(
                "⚠️ برای فعال‌سردن kill-switch تأیید کنید:\n`/kill CONFIRM`",
                parse_mode="Markdown",
            )
            return

        from backend.risk.kill_switch import kill_switch

        kill_switch.activate(reason="Telegram /kill CONFIRM")
        await message.answer(
            "😨 *KILL-SWITCH فعال شد*\nتمام معاملات جدید متوقف شدند.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[control] cmd_kill: %s", exc)
        try:
            await message.answer(f"❌ {exc}")
        except Exception:
            pass


@router.message(Command("positions"))
async def cmd_positions(message: types.Message) -> None:
    """List all active trade positions."""
    try:
        from backend.execution.order_state_machine import order_state_machine

        tickets = order_state_machine.active_tickets()

        if not tickets:
            await message.answer("✅ هیچ پوزیشن باز وجود ندارد.")
            return

        lines = [f"📈 *پوزیشن‌های باز* ({len(tickets)})", ""]
        for t in tickets[:20]:
            state = order_state_machine.get_state(t)
            lines.append(f"• Ticket `{t}` — `{state}`")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[control] cmd_positions: %s", exc)
        await message.answer(f"❌ {exc}")


@router.message(Command("close"))
async def cmd_close(message: types.Message) -> None:
    """
    /close <ticket>

    Close a specific open position by ticket number.
    """
    try:
        args = (message.text or "").split()[1:]
        if not args or not args[0].isdigit():
            await message.answer(
                "⚠️ استفاده: `/close <ticket>`",
                parse_mode="Markdown",
            )
            return

        ticket = int(args[0])
        from backend.execution.execution_service import execution_service

        result = await execution_service.close(ticket)

        if result.success:
            await message.answer(
                f"✅ پوزیشن `{ticket}` بسته شد.",
                parse_mode="Markdown",
            )
        else:
            await message.answer(
                f"❌ بستن `{ticket}` ناموفق: {result.error}",
                parse_mode="Markdown",
            )

    except Exception as exc:
        logger.exception("[control] cmd_close: %s", exc)
        try:
            await message.answer(f"❌ {exc}")
        except Exception:
            pass
