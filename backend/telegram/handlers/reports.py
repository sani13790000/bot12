#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backend/telegram/handlers/reports.py
Telegram Reports Handler
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def handle_daily_report(update: Any, context: Any) -> None:
    """Send daily trading report."""
    await update.message.reply_text(
        "📊 Daily Report\n"
        "Trades: 0\n"
        "PnL: $0.00\n"
        "Win Rate: N/A"
    )


async def handle_weekly_report(update: Any, context: Any) -> None:
    """Send weekly trading report."""
    await update.message.reply_text(
        "📊 Weekly Report\n"
        "Total Trades: 0\n"
        "Net PnL: $0.00\n"
        "Best Day: N/A"
    )


async def handle_performance(update: Any, context: Any) -> None:
    """Send performance metrics."""
    await update.message.reply_text(
        "🏆 Performance Metrics\n"
        "Sharpe Ratio: N/A\n"
        "Max Drawdown: N/A\n"
        "Profit Factor: N/A"
    )
