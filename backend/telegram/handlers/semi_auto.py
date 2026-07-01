"""
backend/telegram/handlers/semi_auto.py
Galaxy Vast AI — Semi-Auto Telegram Handler

Handles signal approval/rejection via Telegram buttons.
NOTE: Restored from corrupted source.
"""
from __future__ import annotations
import logging
from typing import Any, Dict
logger = logging.getLogger(__name__)


async def send_signal_for_approval(bot: Any, chat_id: int, signal: Dict) -> None:
    """Send a signal to Telegram for manual approval."""
    symbol = signal.get("symbol", "?")
    direction = signal.get("direction", "?")
    confidence = signal.get("confidence", 0) * 100
    lot_size = signal.get("lot_size", 0)
    entry = signal.get("entry_price", 0)
    sl = signal.get("stop_loss", 0)
    tp = signal.get("take_profit", 0)
    text = (
        "\U0001f30c <b>Galaxy Vast \u2014 \u0633\u06cc\u06af\u0646\u0627\u0644 \u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631 \u062a\u0623\u06cc\u06cc\u062f</b>\n\n"
        f"\U0001f4ca <b>\u0633\u06cc\u0645\u0628\u0644:</b> {symbol}\n"
        f"\U0001f9ed <b>\u062c\u0647\u062a:</b> {direction}\n"
        f"\U0001f4af <b>\u0627\u0637\u0645\u06cc\u0646\u0627\u0646:</b> {confidence:.1f}%\n"
        f"\U0001f4e6 <b>\u062d\u062c\u0645:</b> {lot_size:.2f} \u0644\u0627\u062a\n"
        f"\U0001f4b0 <b>\u0648\u0631\u0648\u062f:</b> {entry:.5f}\n"
        f"\U0001f6d1 <b>SL:</b> {sl:.5f}\n"
        f"\U0001f3af <b>TP:</b> {tp:.5f}"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.error("send_signal_for_approval error: %s", exc)
