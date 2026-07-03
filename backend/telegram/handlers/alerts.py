"""
backend/telegram/handlers/alerts.py
Galaxy Vast AI — هندلرهای هشدار معاملاتی

مسئولیت‌ها:
  - ارسال هشدار ورود به معامله
  - ارسال هشدار خروج از معامله
  - ارسال هشدار SL / TP
  - ارسال هشدار باز شدن سشن
  - ارسال هشدار کلی ریسک
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot

log = logging.getLogger(__name__)


class AlertSender:
    """Sends formatted trade alerts via Telegram."""

    def __init__(self, bot: Bot, channel_id: int | str) -> None:
        self._bot        = bot
        self._channel_id = channel_id

    async def send_trade_opened(
        self,
        symbol:      str,
        direction:   str,
        entry_price: float,
        sl_price:    Optional[float],
        tp_price:    Optional[float],
        lot_size:    float,
        ticket:      Optional[int]   = None,
        score:       Optional[float] = None,
        reason:      Optional[str]   = None,
    ) -> None:
        emoji        = "🟢" if direction.upper() == "BUY" else "🔴"
        direction_fa = "خرید" if direction.upper() == "BUY" else "فروش"
        sl_pips = round(abs(entry_price - sl_price) / 0.0001, 1) if sl_price else 0
        tp_pips = round(abs(tp_price - entry_price) / 0.0001, 1) if tp_price else 0
        rr      = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0
        lines = [
            f"{emoji} <b>معامله جدید باز شد</b>",
            f"📊 <b>نماد:</b> {symbol}",
            f"📍 <b>جهت:</b> {direction_fa}",
            f"💰 <b>قیمت ورود:</b> {entry_price}",
            f"🛑 <b>استاپ لاس:</b> {sl_price} ({sl_pips:.0f} پیپ)" if sl_price else "🛑 <b>استاپ لاس:</b> —",
            f"🎯 <b>تیک پرافیت:</b> {tp_price} ({tp_pips:.0f} پیپ)" if tp_price else "🎯 <b>تیک پرافیت:</b> —",
            f"📦 <b>حجم لات:</b> {lot_size}",
            f"⚖️ <b>ریسک/ریوارد:</b> 1:{rr}",
        ]
        if ticket:
            lines.append(f"🎟 <b>تیکت:</b> #{ticket}")
        if score:
            lines.append(f"⭐ <b>امتیاز:</b> {score:.1f}/100")
        if reason:
            lines.append(f"📝 <b>دلیل:</b> {reason}")
        lines.append(f"🕐 {self._now_fa()}")
        await self._broadcast("\n".join(lines))

    async def send_trade_closed(
        self,
        symbol:      str,
        direction:   str,
        open_price:  float,
        close_price: float,
        profit:      float,
        pips:        float,
        lot_size:    float,
        ticket:      Optional[int] = None,
        duration:    Optional[str] = None,
    ) -> None:
        profit_emoji = "✅" if profit >= 0 else "❌"
        direction_fa = "خرید" if direction.upper() == "BUY" else "فروش"
        lines = [
            f"{profit_emoji} <b>معامله بسته شد</b>",
            f"📊 <b>نماد:</b> {symbol}",
            f"📍 <b>جهت:</b> {direction_fa}",
            f"💹 <b>ورود:</b> {open_price}  ← →  <b>خروج:</b> {close_price}",
            f"📈 <b>پیپ:</b> {pips:+.1f}",
            f"💵 <b>سود/ضرر:</b> {profit:+.2f} USD",
            f"📦 <b>حجم:</b> {lot_size}",
        ]
        if ticket:
            lines.append(f"🎟 <b>تیکت:</b> #{ticket}")
        if duration:
            lines.append(f"⏱ <b>مدت:</b> {duration}")
        lines.append(f"🕐 {self._now_fa()}")
        await self._broadcast("\n".join(lines))

    async def send_sl_hit(self, symbol: str, ticket: int, price: float) -> None:
        await self._broadcast(
            f"🛑 <b>استاپ لاس فعال شد</b>\n"
            f"📊 {symbol}  |  🎟 #{ticket}\n"
            f"💰 قیمت: {price}\n"
            f"🕐 {self._now_fa()}"
        )

    async def send_tp_hit(self, symbol: str, ticket: int, price: float) -> None:
        await self._broadcast(
            f"🎯 <b>تیک پرافیت فعال شد</b>\n"
            f"📊 {symbol}  |  🎟 #{ticket}\n"
            f"💰 قیمت: {price}\n"
            f"🕐 {self._now_fa()}"
        )

    async def send_session_open(self, session_name: str) -> None:
        await self._broadcast(
            f"🌍 <b>سشن {session_name} باز شد</b>\n"
            f"🕐 {self._now_fa()}"
        )

    async def send_risk_alert(self, message: str, level: str = "WARNING") -> None:
        emoji = {"WARNING": "⚠️", "CRITICAL": "🚨", "INFO": "ℹ️"}.get(level, "⚠️")
        await self._broadcast(
            f"{emoji} <b>هشدار ریسک</b>\n"
            f"{message}\n"
            f"🕐 {self._now_fa()}"
        )

    async def _broadcast(self, text: str) -> None:
        try:
            await self._bot.send_message(
                chat_id=self._channel_id, text=text, parse_mode="HTML",
            )
        except Exception as exc:
            log.error("Alert send failed: %s", exc)

    def _now_fa(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y/%m/%d — %H:%M UTC")
