"""
backend/telegram/handlers/control.py
Galaxy Vast AI — Telegram Control Handlers
NOTE: Auto-repaired stub.
"""
from __future__ import annotations
import logging
_LOG = logging.getLogger(__name__)


async def handle_start(message) -> None:
    await message.answer('Galaxy Vast AI Bot started.')


async def handle_stop(message) -> None:
    await message.answer('Galaxy Vast AI Bot stopping.')


async def handle_status(message) -> None:
    await message.answer('Bot is running.')
