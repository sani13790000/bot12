"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌ Telegram Admin Router ┌
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("admin"))
async def admin_panel(message: Message) -> None:
    """نمایش پنل مدیریت ادمین"""
    user_id = message.from_user.id if message.from_user else None
    logger.info("admin_panel requested by user_id=%s", user_id)
    await message.answer(
        "🛡 <b>Galaxy Vast AI — Admin Panel</b>\n\n"
        "دستورات موجود:\n"
        "/stats — آمار معاملات\n"
        "/kill — Kill Switch فعال\n"
        "/resume — Kill Switch غیرفعال\n"
        "/users — کاربران فعال\n"
        "/health — وضعیت سیستم",
        parse_mode="HTML",
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """نمایش آمار معاملات امروز."""
    from backend.services.trade_service import TradeService

    ts = TradeService()
    stats = await ts.get_stats()
    await message.answer(
        f"📊 <b>آمار امروز</b>\n"
        f"معاملات باز: {stats.get('open', 0)}\n"
        f"معاملات بسته: {stats.get('closed', 0)}\n"
        f"Win Rate: {stats.get('win_rate', 0):.1f}\n"
        f"PnL امروز: {stats.get('daily_pnl', 0):.2f}",
        parse_mode="HTML",
    )


@router.message(Command("kill"))
async def cmd_kill(message: Message) -> None:
    """فعال‌سازی Kill Switch از طریق ادمین."""
    from backend.risk.kill_switch import KillSwitch

    ks = KillSwitch()
    await ks.activate(reason="admin_telegram_command")
    logger.warning(
        "kill_switch.activated by admin user=%s",
        message.from_user.id if message.from_user else "unknown",
    )
    await message.answer("🔴 Kill Switch فعال شد — همه معاملات جدید متوقف شدند.", parse_mode="HTML")


@router.message(Command("resume"))
async def cmd_resume(message: Message) -> None:
    """غیرفعال‌سازی Kill Switch."""
    from backend.risk.kill_switch import KillSwitch

    ks = KillSwitch()
    await ks.deactivate()
    await message.answer("🟢 Kill Switch غیرفعال شد — معاملات از سر گرفته شدند.", parse_mode="HTML")


@router.message(Command("users"))
async def cmd_users(message: Message) -> None:
    """لیست کاربران فعال."""
    from backend.services.session_service import SessionService

    ss = SessionService()
    users = await ss.list_active()
    lines = [f"👤 {u['user_id']} — {u.get('plan', '?')}" for u in users[:20]]
    await message.answer("\n".join(lines) or "هیچ کاربر فعالی یافت نشد.", parse_mode="HTML")


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    """وضعیت سیستم."""
    from backend.database.connection import get_db_health
    from backend.execution.mt5_connector import MT5Connector

    db_ok = await get_db_health()
    mt5_ok = MT5Connector().is_connected()
    valid_icon = "✅ بله" if db_ok else "❌ خیر"
    mt5_icon = "✅ بله" if mt5_ok else "❌ خیر"
    await message.answer(
        f"🏥 <b>وضعیت سیستم</b>\nDatabase: {valid_icon}\nMT5 Gateway: {mt5_icon}", parse_mode="HTML"
    )
