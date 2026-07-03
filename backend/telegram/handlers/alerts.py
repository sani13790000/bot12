"""
=====================================================================
Alerts Handler - Galaxy Vast AI Trading Platform
Version: 3.0 (Production)
Description: Manages Telegram alert notifications for trading events
=====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from aiogram import Bot, Router
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)
router = Router()


class AlertService:
    """
    Sends structured Telegram alerts for trading events.
    Supports: trade open/close, SL/TP hit, session alerts, system alerts.
    """

    def __init__(self, bot: Bot, chat_ids: List[int]) -> None:
        self._bot      = bot
        self._chat_ids = chat_ids

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _now_fa(self) -> str:
        """Return current UTC time as HH:MM UTC."""
        return datetime.now(timezone.utc).strftime("%H:%M UTC")

    async def _broadcast(self, text: str) -> None:
        """Send text to all registered chat IDs."""
        for chat_id in self._chat_ids:
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                )
            except Exception as exc:
                logger.error("[Alert] send error to %s: %s", chat_id, exc)

    # ------------------------------------------------------------------ #
    # Trade alerts
    # ------------------------------------------------------------------ #

    async def trade_opened(
        self,
        symbol:       str,
        direction:    str,
        entry_price:  float,
        sl_price:     float,
        tp_price:     float,
        lot_size:     float,
        sl_pips:      float = 0.0,
        tp_pips:      float = 0.0,
        rr:           float = 0.0,
        ticket:       Optional[int] = None,
        score:        Optional[float] = None,
        reason:       Optional[str] = None,
    ) -> None:
        """Alert for a newly opened trade."""
        emoji         = "\U0001f7e2" if direction.lower() == "buy" else "\U0001f534"
        direction_fa  = "\U0001f4c8 خرید" if direction.lower() == "buy" else "\U0001f4c9 فروش"

        text = (
            f"{emoji} <b>\u0645\u0639\u0627\u0645\u0644\u0647 \u062c\u062f\u06cc\u062f \u0628\u0627\u0632 \u0634\u062f</b>\n"
            f"\U0001f4ca <b>\u0646\u0645\u0627\u062f:</b> {symbol}\n"
            f"\U0001f4cd <b>\u062c\u0647\u062a:</b> {direction_fa}\n"
            f"\U0001f4b0 <b>\u0642\u06cc\u0645\u062a \u0648\u0631\u0648\u062f:</b> {entry_price}\n"
            f"\U0001f6d1 <b>\u0627\u0633\u062a\u067e \u0644\u0627\u0633:</b> {sl_price} ({sl_pips:.0f} \u067e\u06cc\u067e)\n"
            f"\U0001f3af <b>\u062a\u06cc\u06a9 \u067e\u0631\u0627\u0641\u06cc\u062a:</b> {tp_price} ({tp_pips:.0f} \u067e\u06cc\u067e)\n"
            f"\U0001f4e6 <b>\u062d\u062c\u0645 \u0644\u0627\u062a:</b> {lot_size}\n"
            f"\u2696\ufe0f <b>\u0631\u06cc\u0633\u06a9/\u0631\u06cc\u0648\u0627\u0631\u062f:</b> 1:{rr}\n"
        )
        if ticket:
            text += f"\U0001f3ab <b>\u062a\u06cc\u06a9\u062a:</b> #{ticket}\n"
        if score is not None:
            text += f"\u2b50 <b>\u0627\u0645\u062a\u06cc\u0627\u0632:</b> {score:.1f}/100\n"
        if reason:
            text += f"\U0001f4dd <b>\u062f\u0644\u06cc\u0644:</b> {reason}\n"
        text += f"\U0001f550 {self._now_fa()}"

        await self._broadcast(text)
        logger.info("[Alert] trade opened: %s %s", symbol, direction)

    async def trade_closed(
        self,
        symbol:       str,
        direction:    str,
        entry_price:  float,
        close_price:  float,
        profit:       float,
        lot_size:     float,
        pips:         float = 0.0,
        ticket:       Optional[int] = None,
        reason:       str = "",
    ) -> None:
        """Alert for a closed trade."""
        emoji        = "\u2705" if profit >= 0 else "\u274c"
        direction_fa = "\U0001f4c8 خرید" if direction.lower() == "buy" else "\U0001f4c9 فروش"
        profit_fa    = f"+{profit:.2f}$" if profit >= 0 else f"{profit:.2f}$"
        pips_fa      = f"+{pips:.1f} pip" if pips >= 0 else f"{pips:.1f} pip"
        reason_fa    = reason or "manual"

        text = (
            f"{emoji} <b>\u0645\u0639\u0627\u0645\u0644\u0647 \u0628\u0633\u062a\u0647 \u0634\u062f</b>\n"
            f"\U0001f4ca <b>\u0646\u0645\u0627\u062f:</b> {symbol}\n"
            f"\U0001f4cd <b>\u062c\u0647\u062a:</b> {direction_fa}\n"
            f"\U0001f4b0 <b>\u0648\u0631\u0648\u062f:</b> {entry_price}  \u2190  <b>\u062e\u0631\u0648\u062c:</b> {close_price}\n"
            f"\U0001f4b5 <b>\u0646\u062a\u06cc\u062c\u0647:</b> {profit_fa} ({pips_fa})\n"
            f"\U0001f4e6 <b>\u062d\u062c\u0645:</b> {lot_size}\n"
            f"\U0001f4cc <b>\u062f\u0644\u06cc\u0644:</b> {reason_fa}\n"
        )
        if ticket:
            text += f"\U0001f3ab <b>\u062a\u06cc\u06a9\u062a:</b> #{ticket}\n"
        text += f"\U0001f550 {self._now_fa()}"

        await self._broadcast(text)
        logger.info("[Alert] trade closed: %s profit=%s", symbol, profit_fa)

    async def sl_hit(
        self,
        symbol:    str,
        ticket:    Optional[int],
        loss:      float,
        loss_pips: float,
    ) -> None:
        """Alert for a stop-loss hit."""
        text = (
            f"\U0001f6d1 <b>\u0627\u0633\u062a\u067e \u0644\u0627\u0633 \u0632\u062f\u0647 \u0634\u062f!</b>\n"
            f"\U0001f4ca <b>\u0646\u0645\u0627\u062f:</b> {symbol}\n"
        )
        if ticket:
            text += f"\U0001f3ab <b>\u062a\u06cc\u06a9\u062a:</b> #{ticket}\n"
        text += (
            f"\U0001f4b8 <b>\u0636\u0631\u0631:</b> {loss:.2f}$ ({loss_pips:.1f} \u067e\u06cc\u067e)\n"
            f"\U0001f550 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def tp_hit(
        self,
        symbol:      str,
        ticket:      Optional[int],
        profit:      float,
        profit_pips: float,
    ) -> None:
        """Alert for a take-profit hit."""
        text = (
            f"\U0001f3af <b>\u062a\u06cc\u06a9 \u067e\u0631\u0627\u0641\u06cc\u062a \u0632\u062f\u0647 \u0634\u062f!</b>\n"
            f"\U0001f4ca <b>\u0646\u0645\u0627\u062f:</b> {symbol}\n"
        )
        if ticket:
            text += f"\U0001f3ab <b>\u062a\u06cc\u06a9\u062a:</b> #{ticket}\n"
        text += (
            f"\U0001f4b0 <b>\u0633\u0648\u062f:</b> +{profit:.2f}$ (+{profit_pips:.1f} \u067e\u06cc\u067e)\n"
            f"\U0001f550 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def system_alert(
        self,
        level:   str,
        emoji:   str,
        message: str,
    ) -> None:
        """Generic system alert."""
        text = (
            f"{emoji} <b>\u0647\u0634\u062f\u0627\u0631 \u0633\u06cc\u0633\u062a\u0645 [{level}]</b>\n"
            f"{message}\n"
            f"\U0001f550 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def bot_started(self) -> None:
        """Alert sent when the bot starts up."""
        text = (
            f"\U0001f7e2 <b>\u0631\u0628\u0627\u062a \u0645\u0639\u0627\u0645\u0644\u0627\u062a\u06cc \u0634\u0631\u0648\u0639 \u0628\u0647 \u06a9\u0627\u0631 \u06a9\u0631\u062f</b>\n"
            f"\u2705 \u062a\u0645\u0627\u0645 \u0633\u0631\u0648\u06cc\u0633\u200c\u0647\u0627 \u0641\u0639\u0627\u0644 \u0634\u062f\u0646\u062f\n"
            f"\U0001f550 {self._now_fa()}"
        )
        await self._broadcast(text)

    async def bot_stopped(self, reason: str = "") -> None:
        """Alert sent when the bot shuts down."""
        text = (
            f"\U0001f534 <b>\u0631\u0628\u0627\u062a \u0645\u0639\u0627\u0645\u0644\u0627\u062a\u06cc \u0645\u062a\u0648\u0642\u0641 \u0634\u062f</b>\n"
            f"\U0001f4cc {reason or 'shutdown'}\n"
            f"\U0001f550 {self._now_fa()}"
        )
        await self._broadcast(text)


# Module-level singleton (initialised at startup)
alert_service: Optional[AlertService] = None
