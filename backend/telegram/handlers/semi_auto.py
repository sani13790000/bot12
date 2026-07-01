"""
backend/telegram/handlers/semi_auto.py
Galaxy Vast AI — Semi-Auto Trade Handlers
NOTE: Auto-repaired stub.
"""
from __future__ import annotations
import logging
_LOG = logging.getLogger(__name__)


async def handle_approve_trade(message, trade_id: str) -> None:
    await message.answer(f'Trade {trade_id} approved.')


async def handle_reject_trade(message, trade_id: str) -> None:
    await message.answer(f'Trade {trade_id} rejected.')
