"""
backend/telegram/handlers/intelligence.py
Telegram handlers for trade memory and learning stats.
"""
from __future__ import annotations
import logging
import httpx
from aiogram import Router, types
from aiogram.filters import Command
from backend.core.config import settings
from backend.core.logger import get_logger

logger = get_logger(__name__)
router = Router(name="intelligence")
_API_BASE = getattr(settings, "API_BASE_URL", "http://api:8000")


@router.message(Command("memory"))
async def cmd_memory(message: types.Message):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{_API_BASE}/api/v1/learning/stats")
            if response.status_code != 200:
                await message.answer("\u274c \u062e\u0637\u0627 \u062f\u0631 \u062f\u0631\u06cc\u0627\u0641\u062a \u0622\u0645\u0627\u0631", parse_mode="Markdown")
                return
            stats = response.json()
        text = (
            " *Galaxy Vast \u2014 \u062d\u0627\u0641\u0638\u0647 \u06cc\u0627\u062f\u06af\u06cc\u0631\u06cc*\n\n"
            f" *\u06a9\u0644 \u0645\u0639\u0627\u0645\u0644\u0627\u062a:* `{stats.get('total_trades', 0)}`\n"
            f" *\u0628\u0631\u0646\u062f\u0647\u200c\u0647\u0627:* `{stats.get('wins', 0)}`\n"
            f" *\u0628\u0627\u0632\u0646\u062f\u0647\u200c\u0647\u0627:* `{stats.get('losses', 0)}`\n"
            f" *\u0646\u0631\u062e \u0628\u0631\u0646\u062f\u0647:* `{stats.get('win_rate', 0):.1%}`\n"
            f" *\u0645\u06cc\u0627\u0646\u06af\u06cc\u0646 R:R:* `{stats.get('avg_rr', 0):.2f}`\n"
        )
        await message.answer(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Memory handler error: {e}")
        await message.answer("\u274c \u062e\u0637\u0627 \u062f\u0631 \u062f\u0631\u06cc\u0627\u0641\u062a \u0627\u0637\u0644\u0627\u0639\u0627\u062a \u062d\u0627\u0641\u0638\u0647")


@router.message(Command("retrain"))
async def cmd_retrain(message: types.Message):
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{_API_BASE}/api/v1/learning/retrain")
            if response.status_code == 200:
                await message.answer("\u2705 \u0628\u0627\u0632\u0622\u0645\u0648\u0632\u06cc \u0645\u062f\u0644 \u0634\u0631\u0648\u0639 \u0634\u062f")
            else:
                await message.answer("\u274c \u062e\u0637\u0627 \u062f\u0631 \u0634\u0631\u0648\u0639 \u0628\u0627\u0632\u0622\u0645\u0648\u0632\u06cc")
    except Exception as e:
        await message.answer(f"\u274c \u062e\u0637\u0627: {str(e)[:100]}")
