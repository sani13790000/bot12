"""
backend/telegram/handlers/semi_auto.py
Galaxy Vast AI — Semi-Auto Telegram Handler
"""
from __future__ import annotations
import logging
from typing import Any, Dict
logger = logging.getLogger(__name__)

async def send_signal_for_approval(bot: Any, chat_id: int, signal: Dict) -> None:
    symbol = signal.get("symbol", "?")
    direction = signal.get("direction", "?")
    conf = signal.get("confidence", 0) * 100
    lots = signal.get("lot_size", 0)
    entry = signal.get("entry_price", 0)
    text = (
        "\U0001f30c <b>Galaxy Vast \u2014 \u0633\u06cc\u06af\u0646\u0627\u0644</b>\n\n"
        f"\U0001f4ca {symbol} | {direction}\n"
        f"\U0001f4af {conf:.1f}% | \U0001f4e6 {lots:.2f} \u0644\u0627\u062a | \U0001f4b0 {entry:.5f}"
    )
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.error("send_signal_for_approval: %s", exc)
