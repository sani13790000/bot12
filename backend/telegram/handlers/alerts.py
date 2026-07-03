"""
backend/telegram/handlers/alerts.py
Telegram alert handlers for MT5 trading events.

Handles: Trade entry/exit alerts, SL/TP alerts, Session alerts, System alerts.
Version: 2.0.0
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AlertHandler:
    """Sends trading alerts to Telegram admins."""

    def __init__(self, bot=None, admin_ids: list[int] | None = None):
        self._bot = bot
        self._admin_ids: list[int] = admin_ids or []

    async def _broadcast(self, text: str) -> None:
        if not self._bot:
            logger.warning("Bot not initialized, cannot broadcast")
            return
        for admin_id in self._admin_ids:
            try:
                await self._bot.send_message(
                    chat_id=admin_id, text=text, parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Error sending alert to admin {admin_id}: {e}")

    @staticmethod
    def _now_fa() -> str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y/%m/%d \u2014 %H:%M UTC")

    async def send_trade_open(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        sl_price: float,
        tp_price: float,
        lot_size: float,
        ticket: Optional[int] = None,
        score: Optional[float] = None,
        reason: Optional[str] = None,
    ) -> None:
        direction_fa = "\U0001f7e2 \u062e\u0631\u06cc\u062f" if direction.upper() == "BUY" else "\U0001f534 \u0641\u0631\u0648\u0634"
        emoji = "\U0001f7e2" if direction.upper() == "BUY" else "\U0001f534"
        sl_pips = abs(entry_price - sl_price) * 10000
        tp_pips = abs(tp_price - entry_price) * 10000
        rr = round(tp_pips / sl_pips, 2) if sl_pips > 0 else 0
        text = (
            f"{emoji} <b>\u0645\u0639\u0627\u0645\u0644\u0647 \u062c\u062f\u06cc\u062f \u0628\u0627\u0632 \u0634\u062f</b>\n"
            f" <b>\u0646\u0645\u0627\u062f:</b> {symbol}\n"
            f" <b>\u062c\u0647\u062a:</b> {direction_fa}\n"
            f" <b>\u0642\u06cc\u0645\u062a \u0648\u0631\u0648\u062f:</b> {entry_price}\n"
            f" <b>\u0627\u0633\u062a\u0627\u067e \u0644\u0627\u0633:</b> {sl_price} ({sl_pips:.0f} \u067e\u06cc\u067e)\n"
            f" <b>\u062a\u06cc\u06a9 \u067e\u0631\u0627\u0641\u06cc\u062a:</b> {tp_price} ({tp_pips:.0f} \u067e\u06cc\u067e)\n"
            f" <b>\u062d\u062c\u0645 \u0644\u0627\u062a:</b> {lot_size}\n"
            f" <b>\u0631\u06cc\u0633\u06a9/\u0631\u06cc\u0648\u0627\u0631\u062f:</b> 1:{rr}\n"
        )
        if ticket:
            text += f" <b>\u062a\u06cc\u06a9\u062a:</b> #{ticket}\n"
        if score:
            text += f" <b>\u0627\u0645\u062a\u06cc\u0627\u0632:</b> {score:.1f}/100\n"
        if reason:
            text += f" <b>\u062f\u0644\u06cc\u0644:</b> {reason}\n"
        text += f"\n{AlertHandler._now_fa()}"
        await self._broadcast(text)
        logger.info(f"Trade open alert sent: {symbol} {direction}")

    async def send_trade_close(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        close_price: float,
        profit: float,
        lot_size: float,
        ticket: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> None:
        emoji = "\u2705" if profit >= 0 else "\u274c"
        direction_fa = "\u062e\u0631\u06cc\u062f" if direction.upper() == "BUY" else "\u0641\u0631\u0648\u0634"
        profit_str = f"+{profit:.2f}" if profit >= 0 else f"{profit:.2f}"
        text = (
            f"{emoji} <b>\u0645\u0639\u0627\u0645\u0644\u0647 \u0628\u0633\u062a\u0647 \u0634\u062f</b>\n"
            f" <b>\u0646\u0645\u0627\u062f:</b> {symbol}\n"
            f" <b>\u062c\u0647\u062a:</b> {direction_fa}\n"
            f" <b>\u0633\u0648\u062f/\u0632\u06cc\u0627\u0646:</b> {profit_str}\n"
            f" <b>\u062d\u062c\u0645 \u0644\u0627\u062a:</b> {lot_size}\n"
        )
        if reason:
            text += f" <b>\u062f\u0644\u06cc\u0644 \u0628\u0633\u062a\u0646:</b> {reason}\n"
        text += f"\n{AlertHandler._now_fa()}"
        await self._broadcast(text)
        logger.info(f"Trade close alert sent: {symbol} profit={profit:.2f}")

    async def send_system_alert(self, message: str, level: str = "INFO") -> None:
        icons = {"INFO": "\u2139\ufe0f", "WARNING": "\u26a0\ufe0f", "ERROR": "\u274c", "CRITICAL": "\U0001f6a8"}
        icon = icons.get(level.upper(), "\u2139\ufe0f")
        text = (
            f"{icon} <b>\u0647\u0634\u062f\u0627\u0631 \u0633\u06cc\u0633\u062a\u0645 [{level}]</b>\n"
            f"{message}\n"
            f"\n{AlertHandler._now_fa()}"
        )
        await self._broadcast(text)


alert_handler: AlertHandler = AlertHandler()
