"""
backend/telegram/handlers/reports.py
Galaxy Vast AI — Telegram Report Handlers
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

_LOG = logging.getLogger(__name__)


async def send_daily_report(bot, chat_id: int, stats: Dict[str, Any]) -> None:
    pnl = stats.get('total_pnl', 0.0)
    trades = stats.get('total_trades', 0)
    win_rate = stats.get('win_rate', 0.0)
    text = (
        '<b>Daily Report</b>\n'
        f'Total PnL: {pnl:.2f}\n'
        f'Trades: {trades}\n'
        f'Win Rate: {win_rate:.1%}'
    )
    await bot.send_message(chat_id, text)


async def send_weekly_report(bot, chat_id: int, stats: Dict[str, Any]) -> None:
    text = '<b>Weekly Report</b>\nStats: ' + str(stats)
    await bot.send_message(chat_id, text)


async def send_performance_summary(bot, chat_id: int, data: Dict[str, Any]) -> None:
    text = '<b>Performance Summary</b>\n' + str(data)
    await bot.send_message(chat_id, text)


async def handle_report_command(message, report_type: str = 'daily') -> None:
    await message.answer(f'Generating {report_type} report...')
