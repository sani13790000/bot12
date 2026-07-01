"""
backend/telegram/routers/admin.py
Galaxy Vast AI — Admin Commands
"""
from __future__ import annotations
import logging, os
from typing import Any, Set
logger = logging.getLogger(__name__)
_ADMIN_IDS: Set[int] = {
    int(x.strip()) for x in os.getenv("TELEGRAM_ADMIN_IDS","").split(",") if x.strip().isdigit()
}
def is_admin(uid): return uid in _ADMIN_IDS
async def cmd_admin_stats(message,stats):
    if not is_admin(message.from_user.id):
        await message.answer("\u274c Access denied"); return
    lines=["\U0001f511 <b>Admin Stats</b>\n"]+[f"  {k}: {v}" for k,v in stats.items()]
    try: await message.answer("\n".join(lines),parse_mode="HTML")
    except Exception as e: logger.error("admin_stats: %s",e)
async def cmd_kill_switch(message,engine):
    if not is_admin(message.from_user.id):
        await message.answer("\u274c Access denied"); return
    await engine.activate_kill_switch(admin_id=str(message.from_user.id),reason="manual")
    await message.answer("\U0001f6a8 <b>Kill switch activated</b>",parse_mode="HTML")
