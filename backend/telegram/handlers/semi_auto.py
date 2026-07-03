"""
========================================================
Semi-Auto Handler - Galaxy Vast AI Trading Platform
Handles semi-automatic trade confirmation via Telegram
========================================================
"""
from __future__ import annotations

import logging
from typing import Optional

from aiogram import Router, types
from aiogram.filters import callback_query
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from ...core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = Router()


def get_confirm_keyboard(signal_id: str) -> InlineKeyboardMarkup:
    """Build approve/reject keyboard for a signal."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="\u2705 \u062a\u0623\u06cc\u06cc\u062f",
                    callback_data=f"semi_auto:approve:{signal_id}",
                ),
                InlineKeyboardButton(
                    text="\u274c \u0631\u062f",
                    callback_data=f"semi_auto:reject:{signal_id}",
                ),
            ]
        ]
    )


def format_signal_message(signal: dict) -> str:
    """Format a signal for Telegram display."""
    direction = signal.get("action", signal.get("direction", ""))
    direction_emoji = "\U0001f4c8" if direction.lower() == "buy" else "\U0001f4c9"
    direction_fa = "\u062e\u0631\u06cc\u062f" if direction.lower() == "buy" else "\u0641\u0631\u0648\u0634"

    lines = [
        f"\U0001f30c <b>Galaxy Vast \u2014 \u0633\u06cc\u06af\u0646\u0627\u0644 \u062f\u0631 \u0627\u0646\u062a\u0638\u0627\u0631 \u062a\u0623\u06cc\u06cc\u062f</b>",
        f"{direction_emoji} <b>\u062c\u0647\u062a:</b> {direction_fa}",
        f"\U0001f4ca <b>\u0646\u0645\u0627\u062f:</b> {signal.get('symbol', '')}",
        f"\U0001f4b0 <b>\u0642\u06cc\u0645\u062a \u0648\u0631\u0648\u062f:</b> {signal.get('entry_price', 0):.5f}",
        f"\U0001f6d1 <b>\u0627\u0633\u062a\u067e \u0644\u0627\u0633:</b> {signal.get('stop_loss', 0):.5f}",
        f"\U0001f3af <b>\u062a\u06cc\u06a9 \u067e\u0631\u0627\u0641\u06cc\u062a:</b> {signal.get('take_profit_1', signal.get('take_profit', 0)):.5f}",
        f"\U0001f4e6 <b>\u062d\u062c\u0645:</b> {signal.get('lot_size', 0):.2f} \u0644\u0627\u062a",
        f"\u26a0\ufe0f <b>\u0631\u06cc\u0633\u06a9:</b> {signal.get('risk_percent', 0):.1f}\u0025",
        f"\U0001f9e0 <b>\u0627\u0645\u062a\u06cc\u0627\u0632 \u0627\u0637\u0645\u06cc\u0646\u0627\u0646:</b> {signal.get('confidence_score', 0):.0f}\u0025",
    ]
    return "\n".join(lines)


@router.callback_query(lambda c: c.data and c.data.startswith("semi_auto:approve:"))
async def handle_approve(callback: types.CallbackQuery) -> None:
    """Handle trade approval."""
    signal_id = callback.data.split(":")[2]
    await callback.answer("\u2705 \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f")
    await callback.message.edit_text(
        f"\u2705 <b>\u0633\u06cc\u06af\u0646\u0627\u0644 \u062a\u0623\u06cc\u06cc\u062f \u0634\u062f</b>\n\u0622\u06cc\u062f\u06cc: {signal_id}",
        parse_mode="HTML",
    )
    logger.info("[SemiAuto] signal approved: %s by user %s", signal_id, callback.from_user.id)


@router.callback_query(lambda c: c.data and c.data.startswith("semi_auto:reject:"))
async def handle_reject(callback: types.CallbackQuery) -> None:
    """Handle trade rejection."""
    signal_id = callback.data.split(":")[2]
    await callback.answer("\u274c \u0631\u062f \u0634\u062f")
    await callback.message.edit_text(
        f"\u274c <b>\u0633\u06cc\u06af\u0646\u0627\u0644 \u0631\u062f \u0634\u062f</b>\n\u0622\u06cc\u062f\u06cc: {signal_id}",
        parse_mode="HTML",
    )
    logger.info("[SemiAuto] signal rejected: %s by user %s", signal_id, callback.from_user.id)
