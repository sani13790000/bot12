"""
backend/telegram/handlers/semi_auto.py
Galaxy Vast AI — Semi-Auto Handler
"""
from __future__ import annotations
import logging
from typing import Any, Dict
logger = logging.getLogger(__name__)
async def send_signal_for_approval(bot,chat_id,signal):
    s=signal.get("symbol","?"); d=signal.get("direction","?")
    c=signal.get("confidence",0)*100; lots=signal.get("lot_size",0)
    e=signal.get("entry_price",0)
    text=("\U0001f30c <b>Signal Pending Approval</b>\n\n"
          f"\U0001f4ca {s} | {d}\n"
          f"\U0001f4af {c:.1f}% | \U0001f4e6 {lots:.2f} lots | \U0001f4b0 {e:.5f}")
    try: await bot.send_message(chat_id=chat_id,text=text,parse_mode="HTML")
    except Exception as exc: logger.error("send_signal_for_approval: %s",exc)
