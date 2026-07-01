"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI — Telegram Intelligence Handlers
NOTE: Auto-repaired stub.
"""
from __future__ import annotations
import logging
_LOG = logging.getLogger(__name__)


async def handle_signal_request(message, symbol: str) -> None:
    await message.answer(f'Analyzing {symbol}...')


async def handle_market_analysis(message) -> None:
    await message.answer('Market analysis not available.')
