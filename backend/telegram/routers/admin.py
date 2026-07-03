"""
backend/telegram/routers/admin.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Admin-only Telegram Router (aiogram v3).

Commands
--------
/admin_stats    – live system statistics
/admin_users    – list registered users
/admin_kill     – emergency kill switch (SUPER_ADMIN only)
/admin_restart  – restart trading engine (ADMIN only)
/admin_license  – license status (ADMIN only)
"""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

from ...core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = Router()


# ── /admin_stats ────────────────────────────────────────────────────── #

@router.message(Command("admin_stats"))
@require_permission(Permission.ADMIN)
async def cmd_admin_stats(message: types.Message) -> None:
    """Show live system statistics (ADMIN only)."""
    lines = ["📊 *System Status*\n"]

    # Kill-switch
    try:
        from backend.risk.kill_switch import kill_switch
        ks = "🐂 ACTIVE" if kill_switch.is_active() else "🔴 INACTIVE"
        lines.append(f"🛑️ Kill-Switch: `{ks}`")
    except Exception as exc:
        logger.warning("[admin] kill_switch check failed: %s", exc)
        lines.append("🛑️ Kill-Switch: `unknown`")

    # Open positions
    try:
        from backend.execution.order_state_machine import order_state_machine
        count = len(order_state_machine.active_tickets())
        lines.append(f"📈 Open Positions: `{count}`")
    except Exception as exc:
        logger.warning("[admin] order_state_machine check failed: %s", exc)
        lines.append("📈 Open Positions: `unknown`")

    # Scheduler tasks
    try:
        from backend.services.scheduler import scheduler
        n = len(scheduler._tasks)  # noqa: SLF001
        lines.append(f"⏰ Scheduler Tasks: `{n}`")
    except Exception as exc:
        logger.warning("[admin] scheduler check failed: %s", exc)
        lines.append("⏰ Scheduler: `unknown`")

    # Database ping
    try:
        from backend.database.client import db_client
        await db_client.ping()
        lines.append("🗄️ Database: `Connected ✅`")
    except Exception as exc:
        logger.warning("[admin] db ping failed: %s", exc)
        lines.append("🗄️ Database: `Error ❌`")

    # License
    try:
        from backend.license.engine import license_engine
        valid = license_engine.is_valid()
        lines.append(f"🔑 License: `{'Valid ✅' if valid else 'INVALID ❌'}`")
    except Exception as exc:
        logger.warning("[admin] license check failed: %s", exc)
        lines.append("🔑 License: `unknown`")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# ── /admin_users ────────────────────────────────────────────────────── #

@router.message(Command("admin_users"))
@require_permission(Permission.ADMIN)
async def cmd_admin_users(message: types.Message) -> None:
    """List registered users (ADMIN only)."""
    try:
        from backend.database.client import db_client
        rows = await db_client.select(
            "users",
            limit=20,
            order="created_at.desc",
        )
        if not rows:
            await message.answer("✅ هیچ کاربری ثبت نشده.")
            return

        lines = [f"👥 *کاربران ثبت‌شده* ({len(rows)})\n"]
        for r in rows:
            uid   = str(r.get("id", "?"))[:8]
            email = r.get("email", "?")
            role  = r.get("role", "user")
            lines.append(f"• `{uid}` — {email} — *{role}*")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[admin] cmd_admin_users: %s", exc)
        await message.answer(f"❌ خطا: {exc}")


# ── /admin_kill ─────────────────────────────────────────────────────── #

@router.message(Command("admin_kill"))
@require_permission(Permission.SUPER_ADMIN)
async def cmd_admin_kill(message: types.Message) -> None:
    """Activate emergency kill switch (SUPER_ADMIN only)."""
    try:
        from backend.risk.kill_switch import kill_switch
        kill_switch.activate(
            reason=f"Telegram /admin_kill by {message.from_user.id}"  # type: ignore[union-attr]
        )
        logger.critical(
            "[Admin] kill switch activated by user %s",
            message.from_user.id,  # type: ignore[union-attr]
        )
        await message.answer(
            "😨 *KILL SWITCH ACTIVATED ⚠️*\n"
            "تمام معاملات جدید مسدود شدند.\n"
            "پوزیشن‌های موجود باز می‌مانند.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[admin] cmd_admin_kill: %s", exc)
        await message.answer(f"❌ خطا: {exc}")


# ── /admin_restart ─────────────────────────────────────────────────── #

@router.message(Command("admin_restart"))
@require_permission(Permission.ADMIN)
async def cmd_admin_restart(message: types.Message) -> None:
    """Restart trading engine (ADMIN only)."""
    try:
        logger.warning(
            "[Admin] restart requested by user %s",
            message.from_user.id,  # type: ignore[union-attr]
        )
        from backend.risk.kill_switch import kill_switch
        from backend.services.scheduler import scheduler

        kill_switch.deactivate()
        await scheduler.start()

        await message.answer(
            "♻️ موتور معاملاتی *راه‌اندازی مجدد* شد.\n"
            "Kill-switch غیرفعال، Scheduler فعال.",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[admin] cmd_admin_restart: %s", exc)
        await message.answer(f"❌ خطا: {exc}")


# ── /admin_license ────────────────────────────────────────────────── #

@router.message(Command("admin_license"))
@require_permission(Permission.ADMIN)
async def cmd_admin_license(message: types.Message) -> None:
    """Show license status (ADMIN only)."""
    try:
        from backend.license.engine import license_engine
        status = license_engine.status()

        lines = [
            "🔑 *وضعیت لایسنس*\n",
            f"معتبر: `{'\u2705 بله' if status.get('valid') else '\u274c خیر'}`",
            f"شناسه: `{status.get('license_id', 'N/A')}`",
            f"انقضا: `{status.get('expires_at', 'N/A')}`",
            f"آخرین heartbeat: `{status.get('last_heartbeat', 'N/A')}`",
        ]
        await message.answer("\n".join(lines), parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[admin] cmd_admin_license: %s", exc)
        await message.answer(f"❌ خطا: {exc}")
