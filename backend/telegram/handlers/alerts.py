"""
backend/telegram/handlers/alerts.py
Galaxy Vast AI — Telegram Alert Handlers
NOTE: Auto-repaired stub.
"""
from __future__ import annotations
import logging
_LOG = logging.getLogger(__name__)


async def send_trade_opened(bot, chat_id: int, trade: dict) -> None:
    symbol = trade.get('symbol', 'N/A')
    direction = trade.get('direction', 'N/A')
    await bot.send_message(chat_id, f'Trade Opened: {symbol} {direction}')


async def send_trade_closed(bot, chat_id: int, trade: dict) -> None:
    symbol = trade.get('symbol', 'N/A')
    pnl = trade.get('pnl', 0.0)
    await bot.send_message(chat_id, f'Trade Closed: {symbol} PnL: {pnl}')


async def send_risk_alert(bot, chat_id: int, message: str) -> None:
    await bot.send_message(chat_id, f'RISK ALERT: {message}')
