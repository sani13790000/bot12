"""
backend/telegram/handlers/alerts.py
Galaxy Vast AI - Telegram Alert Handlers
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)


def _now_fa() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


def _direction_fa(direction: str) -> tuple:
    if direction.upper() in ("BUY", "LONG"):
        return "📈", "خرید"
    return "📉", "فروش"


class AlertService:
    """Sends structured Telegram alerts for all trading events."""

    def __init__(self, bot: Bot, channel_id: str) -> None:
        self._bot        = bot
        self._channel_id = channel_id

    async def trade_opened(
        self, *, symbol: str, direction: str, entry_price: float,
        sl_price: float, tp_price: float, lot: float,
        score: Optional[float] = None, reason: Optional[str] = None,
    ) -> None:
        dir_emoji, direction_fa = _direction_fa(direction)
        sl_pips = abs(entry_price - sl_price) * 10_000
        tp_pips = abs(tp_price - entry_price) * 10_000
        rr      = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0
        lines = [
            "🚀 <b>معامله جدید باز شد</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>نماد:</b> {symbol}",
            f"{dir_emoji} <b>جهت:</b> {direction_fa}",
            f"💰 <b>قیمت ورود:</b> {entry_price:.5f}",
            f"🛑 <b>حد ضرر:</b>   {sl_price:.5f}",
            f"🎯 <b>هدف:</b>      {tp_price:.5f}",
            f"📦 <b>حجم:</b>      {lot:.2f} لات",
            f"⚖️ <b>R:R نسبت:</b> 1:{rr}",
        ]
        if score is not None:
            lines.append(f"⭐ <b>امتیاز:</b> {score:.1f}/100")
        if reason:
            lines.append(f"📝 <b>دلیل:</b> {reason}")
        lines.append(f"🕐 {_now_fa()}")
        await self._broadcast("\n".join(lines))

    async def trade_closed(
        self, *, symbol: str, direction: str, pnl: float,
        pips: float, duration: str = "", reason: str = "TP/SL",
    ) -> None:
        dir_emoji, direction_fa = _direction_fa(direction)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        sign      = "+" if pnl >= 0 else ""
        lines = [
            f"{pnl_emoji} <b>معامله بسته شد</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>نماد:</b>   {symbol}",
            f"{dir_emoji} <b>جهت:</b>    {direction_fa}",
            f"💵 <b>سود/ضرر:</b> {sign}{pnl:.2f}$",
            f"📏 <b>پیپ:</b>     {sign}{pips:.1f}",
            f"⏱️ <b>مدت:</b>     {duration}",
            f"🏁 <b>دلیل:</b>    {reason}",
            f"🕐 {_now_fa()}",
        ]
        await self._broadcast("\n".join(lines))

    async def risk_alert(self, *, level: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        level_map = {"CRITICAL": ("🚨", "بحرانی"), "HIGH": ("⚠️", "بالا"), "MEDIUM": ("🟡", "متوسط"), "LOW": ("🔵", "پایین")}
        emoji, level_fa = level_map.get(level.upper(), ("⚠️", level))
        lines = [f"{emoji} <b>هشدار ریسک - {level_fa}</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━", f"📋 {message}"]
        if details:
            for k, v in details.items():
                lines.append(f"  {k}: {v}")
        lines.append(f"🕐 {_now_fa()}")
        await self._broadcast("\n".join(lines))

    async def kill_switch_triggered(self, reason: str) -> None:
        lines = ["🛑 <b>KILL SWITCH فعال شد</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━", "⚡ تمام معاملات متوقف شدند", f"📋 دلیل: {reason}", f"🕐 {_now_fa()}"]
        await self._broadcast("\n".join(lines))
        logger.critical("KILL SWITCH triggered: %s", reason)

    async def daily_summary(self, *, total_trades: int, winners: int, losers: int, net_pnl: float, win_rate: float) -> None:
        pnl_emoji = "🟢" if net_pnl >= 0 else "🔴"
        wr_emoji  = "🟢" if win_rate >= 60 else ("🟡" if win_rate >= 50 else "🔴")
        sign      = "+" if net_pnl >= 0 else ""
        lines = [
            "📊 <b>خلاصه روزانه</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📈 <b>کل معاملات:</b>  {total_trades}",
            f"✅ <b>برنده:</b>       {winners}",
            f"❌ <b>بازنده:</b>      {losers}",
            f"{wr_emoji} <b>وین ریت:</b>    {win_rate:.1f}%",
            f"{pnl_emoji} <b>سود/ضرر خالص:</b> {sign}{net_pnl:.2f}$",
            f"🕐 {_now_fa()}",
        ]
        await self._broadcast("\n".join(lines))

    async def system_event(self, event: str, details: str = "") -> None:
        lines = ["⚙️ <b>رویداد سیستم</b>", "━━━━━━━━━━━━━━━━━━━━━━━━━", f"📋 {event}"]
        if details:
            lines.append(f"ℹ️ {details}")
        lines.append(f"🕐 {_now_fa()}")
        await self._broadcast("\n".join(lines))

    async def _broadcast(self, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=self._channel_id, text=text, parse_mode=ParseMode.HTML)
        except Exception as exc:
            logger.error("Telegram broadcast failed: %s", exc)
