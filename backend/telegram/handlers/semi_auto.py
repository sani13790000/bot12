"""
backend/telegram/handlers/semi_auto.py
Galaxy Vast AI - Semi-Automatic Trading Telegram Handlers

Allows operators to confirm or reject signals before execution.
"""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

logger = logging.getLogger(__name__)
router = Router()


def _signal_keyboard(signal_id: str) -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ تایید معامله",  callback_data=f"confirm_signal:{signal_id}")
    builder.button(text="❌ رد سیگنال",   callback_data=f"reject_signal:{signal_id}")
    builder.adjust(2)
    return builder.as_markup()


def format_signal_message(signal: dict) -> str:
    """Format a trading signal for Telegram display."""
    direction_emoji = "📈" if signal["action"] == "BUY" else "📉"
    direction_fa    = "خرید" if signal["action"] == "BUY" else "فروش"
    lines = [
        f"🌌 <b>Galaxy Vast - سیگنال در انتظار تایید</b>",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{direction_emoji} <b>جهت:</b>      {direction_fa}",
        f"📊 <b>نماد:</b>     {signal['symbol']}",
        f"💰 <b>ورود:</b>     {signal.get('entry', 'N/A')}",
        f"🛑 <b>حد ضرر:</b> {signal.get('sl', 'N/A')}",
        f"🎯 <b>هدف:</b>      {signal.get('tp', 'N/A')}",
        f"⭐ <b>امتیاز:</b>   {signal.get('score', 0):.1f}/100",
        f"📝 <b>دلیل:</b>     {signal.get('reason', 'N/A')}",
    ]
    return "\n".join(lines)


@router.message(Command("pending_signals"))
async def cmd_pending_signals(message: types.Message) -> None:
    """Show all pending signals awaiting confirmation."""
    try:
        from backend.services.decision_service import DecisionService
        signals = await DecisionService().get_pending_signals()
        if not signals:
            await message.answer("هیچ سیگنال در انتظار تایید وجود ندارد")
            return
        for sig in signals:
            text = format_signal_message(sig)
            await message.answer(
                text,
                parse_mode   = "HTML",
                reply_markup = _signal_keyboard(sig["id"]),
            )
    except Exception as exc:
        logger.error("pending_signals error: %s", exc)
        await message.answer(f"خطا: {exc}")


@router.callback_query(lambda c: c.data.startswith("confirm_signal:"))
async def on_confirm_signal(callback: types.CallbackQuery) -> None:
    """Execute a confirmed signal."""
    signal_id = callback.data.split(":", 1)[1]
    await callback.answer()
    try:
        from backend.services.decision_service import DecisionService
        result = await DecisionService().execute_signal(signal_id)
        await callback.message.edit_text(
            f"✅ <b>سیگنال تایید شد</b>\nتیکت: {result.get('ticket', 'N/A')}",
            parse_mode="HTML",
        )
        logger.info("Signal %s confirmed and executed", signal_id)
    except Exception as exc:
        logger.error("confirm_signal error: %s", exc)
        await callback.message.edit_text(f"خطا در اجرا: {exc}")


@router.callback_query(lambda c: c.data.startswith("reject_signal:"))
async def on_reject_signal(callback: types.CallbackQuery) -> None:
    """Reject a pending signal."""
    signal_id = callback.data.split(":", 1)[1]
    await callback.answer()
    try:
        from backend.services.decision_service import DecisionService
        await DecisionService().reject_signal(signal_id)
        await callback.message.edit_text(
            f"❌ <b>سیگنال رد شد</b>\nسیگنال {signal_id} لغو شد",
            parse_mode="HTML",
        )
        logger.info("Signal %s rejected", signal_id)
    except Exception as exc:
        await callback.message.edit_text(f"خطا: {exc}")
