"""
backend/telegram/handlers/alerts.py
Galaxy Vast AI — Telegram Alert Handlers
"""
from __future__ import annotations
import logging
from typing import Any, Dict
logger = logging.getLogger(__name__)
async def send_trade_open_alert(bot: Any, chat_id: int, trade: Dict) -> None:
    emoji = "\U0001f7e2" if trade.get("direction")=="BUY" else "\U0001f534"
    s=trade.get("symbol","?"); d=trade.get("direction","?")
    e=trade.get("entry_price",0); sl=trade.get("stop_loss",0); tp=trade.get("take_profit",0)
    lots=trade.get("lot_size",0); conf=trade.get("confidence",0)*100; score=trade.get("score",0)
    text=(f"{emoji} <b>Trade Open</b>\n\n"
          f"\U0001f4ca {s} | {d}\n"
          f"\U0001f4b0 Entry: {e:.5f} | SL: {sl:.5f} | TP: {tp:.5f}\n"
          f"\U0001f4e6 {lots:.2f} lots | \U0001f4af {conf:.1f}% | \u2b50 {score:.1f}/100")
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as exc:
        logger.error("send_trade_open_alert: %s", exc)
async def send_drawdown_alert(bot,chat_id,dd,eq):
    try: await bot.send_message(chat_id=chat_id,text=f"\u26a0\ufe0f Drawdown {dd:.1f}% | ${eq:,.2f}",parse_mode="HTML")
    except Exception as e: logger.error("drawdown_alert: %s",e)
async def send_kill_switch_alert(bot,chat_id,reason,admin):
    try: await bot.send_message(chat_id=chat_id,text=f"\U0001f6a8 KILL SWITCH | {reason} | {admin}",parse_mode="HTML")
    except Exception as e: logger.error("kill_switch_alert: %s",e)
