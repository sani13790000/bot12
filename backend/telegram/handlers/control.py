"""
backend/telegram/handlers/control.py
Galaxy Vast AI — Telegram Control Handlers
"""
from __future__ import annotations
import logging
from typing import Any, Dict
logger = logging.getLogger(__name__)
async def cmd_start_bot(message,bot_state):
    bot_state["running"]=True
    try: await message.answer("\u2705 <b>Bot Active</b>",parse_mode="HTML")
    except Exception as e: logger.error("cmd_start_bot: %s",e)
async def cmd_stop_bot(message,bot_state):
    bot_state["running"]=False
    try: await message.answer("\u26a0\ufe0f <b>Bot Paused</b>",parse_mode="HTML")
    except Exception as e: logger.error("cmd_stop_bot: %s",e)
async def cmd_status(message,bot_state):
    running=bot_state.get("running",False)
    icon="\u2705" if running else "\u23f8\ufe0f"
    mode=bot_state.get("mode","auto")
    try: await message.answer(f"\U0001f916 Status: {icon} | Mode: {mode}",parse_mode="HTML")
    except Exception as e: logger.error("cmd_status: %s",e)
