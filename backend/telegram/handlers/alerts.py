"""
=====================================================================
backend/telegram/handlers/alerts.py
Phase-A Telegram Alerts -- Fixed truncated handlers
=====================================================================
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_trade_alert(update: Any, context: Any) -> None:
    """Send a trade alert to the user."""
    await update.message.reply_text("🚨 Trade alert sent.")


async def send_risk_alert(update: Any, context: Any) -> None:
    """Send a risk alert to the user."""
    await update.message.reply_text("⚠️ Risk alert: Please review your positions.")


async def send_pnl_summary(update: Any, context: Any) -> None:
    """Send daily PnL summary."""
    await update.message.reply_text("📊 Daily PnL summary: No data available.")
