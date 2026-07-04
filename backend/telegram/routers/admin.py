"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Telegram Admin Router — Admin Router
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations
import logging
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from backend.telegram.middlewares import IsAdmin

logger = logging.getLogger(__name__)
router = Router()
router.message.filter(IsAdmin())


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """نمایش آمار کلی ربات به ادمین."""
    from backend.services.trade_service import TradeService
    ts = TradeService()
    stats = await ts.get_stats()
    await message.answer(
        f"📊 <b>آمار کلی</b>\n"
        f"معاملات باز: {stats.get('open', 0)}\n"
        f"معاملات بسته: {stats.get('closed', 0)}\n"
        f"Win Rate: {stats.get('win_rate', 0):.1%}\n"
        f"PnL امروز: {stats.get('daily_pnl', 0):.2f}",
        parse_mode="HTML"
    )


@router.message(Command("kill"))
async def cmd_kill(message: Message) -> None:
    """فعال‌سازی Kill Switch از طریق ادمین."""
    from backend.risk.kill_switch import KillSwitch
    ks = KillSwitch()
    await ks.activate(reason="admin_telegram_command")
    logger.warning("kill_switch.activated by admin user=%s", message.from_user.id if message.from_user else "unknown")
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
    lines = [f"👤 {u['user_id']} — {u.get('plan','?')}" for u in users[:20]]
    await message.answer("\n".join(lines) or "هیچ کاربر فعالی یافت نشد.", parse_mode="HTML")


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    """وضعیت سیستم."""
    from backend.database.connection import get_db_health
    from backend.execution.mt5_connector import MT5Connector
    db_ok = await get_db_health()
    mt5_ok = MT5Connector().is_connected()
    valid_icon = "✅ بله" if db_ok else "❌ خیر"
    mt5_icon  = "✅ بله" if mt5_ok else "❌ خیر"
    await message.answer(
        f"🖥 <b>وضعیت سیستم</b>\n"
        f"Database: {valid_icon}\n"
        f"MT5 Gateway: {mt5_icon}",
        parse_mode="HTML"
    )
