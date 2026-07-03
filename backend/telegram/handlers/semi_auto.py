"""
backend/telegram/handlers/semi_auto.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Semi-automatic trading handlers.

In semi-auto mode the bot surfaces a trade signal to the operator who
then approves or rejects it via an inline keyboard.

Flow
----
1. Bot posts signal with [Approve] [Reject] buttons.
2. Operator presses a button → callback triggers approve/reject handler.
3. On Approve → ExecutionService.execute() is called.
4. On Reject  → signal is logged as rejected.

Commands
--------
/semiauto on|off   — enable / disable semi-auto mode
/pending           — list pending approval signals
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory store: signal_id → signal dict (production: use Redis/DB)
_pending_signals: dict[str, dict] = {}


# ── Semi-auto mode toggle ─────────────────────────────────────────────── #

_semi_auto_enabled: bool = False


async def cmd_semiauto(update: object, context: object) -> None:
    """
    /semiauto [on|off]

    Toggle semi-automatic approval mode.
    """
    global _semi_auto_enabled  # noqa: PLW0603
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args = ctx.args or []
        arg  = args[0].lower() if args else ""

        if arg == "on":
            _semi_auto_enabled = True
            await upd.message.reply_text(
                "✅ حالت نیمه‌خودکار *فعال* شد.\n"
                "سیگنال‌ها برای تأیید ارسال خواهند شد.",
                parse_mode="Markdown",
            )
        elif arg == "off":
            _semi_auto_enabled = False
            await upd.message.reply_text(
                "❌ حالت نیمه‌خودکار *غیرفعال* شد.",
                parse_mode="Markdown",
            )
        else:
            state = "✅ فعال" if _semi_auto_enabled else "❌ غیرفعال"
            await upd.message.reply_text(
                f"🤖 نیمه‌خودکار: {state}\n"
                "*استفاده:* `/semiauto on` | `/semiauto off`",
                parse_mode="Markdown",
            )

    except Exception as exc:
        logger.exception("[semi_auto] cmd_semiauto: %s", exc)


async def cmd_pending(update: object, context: object) -> None:
    """
    /pending

    List all signals awaiting operator approval.
    """
    try:
        if not _pending_signals:
            await update.message.reply_text("✅ هیچ سیگنالی در انتظار تأیید نیست.")  # type: ignore
            return

        lines = [f"⏳ *سیگنال‌های منتظر* ({len(_pending_signals)})", ""]
        for sig_id, sig in list(_pending_signals.items())[:10]:
            symbol    = sig.get("symbol", "?")
            direction = sig.get("direction", "?")
            conf      = sig.get("confidence", 0.0) * 100
            lines.append(
                f"• `{sig_id[:8]}` — *{symbol}* {direction} `{conf:.0f}%`"
            )

        await update.message.reply_text(  # type: ignore
            "\n".join(lines), parse_mode="Markdown"
        )

    except Exception as exc:
        logger.exception("[semi_auto] cmd_pending: %s", exc)


# ── Signal push (called by the signal dispatcher) ─────────────────────── #


async def push_signal_for_approval(
    bot: object,
    chat_id: int,
    signal: dict,
    signal_id: str,
) -> None:
    """
    Send a signal card with Approve / Reject inline buttons.

    The signal dict must contain at minimum:
        symbol, direction, confidence, entry_price (optional),
        sl_price (optional), tp_price (optional)
    """
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        _pending_signals[signal_id] = signal

        symbol    = signal.get("symbol", "?")
        direction = signal.get("direction", "?")
        conf      = signal.get("confidence", 0.0) * 100
        entry     = signal.get("entry_price")
        sl        = signal.get("sl_price")
        tp        = signal.get("tp_price")

        lines = [
            f"⚡ *سیگنال جدید — {symbol}*",
            f"🌀 جهت: `{direction}`",
            f"🎯 اطمینان: `{conf:.0f}%`",
        ]
        if entry:
            lines.append(f"📍 ورود: `{entry:.5f}`")
        if sl:
            lines.append(f"🛡️ SL: `{sl:.5f}`")
        if tp:
            lines.append(f"🏁 TP: `{tp:.5f}`")

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تأیید", callback_data=f"approve:{signal_id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"reject:{signal_id}"),
        ]])

        await bot.send_message(  # type: ignore
            chat_id=chat_id,
            text="\n".join(lines),
            parse_mode="Markdown",
            reply_markup=keyboard,
        )

    except Exception as exc:
        logger.warning("[semi_auto] push_signal_for_approval failed: %s", exc)


# ── Inline keyboard callback ─────────────────────────────────────────────── #


async def callback_signal_decision(update: object, context: object) -> None:
    """
    Handle [Approve] / [Reject] button presses.

    Callback data format: ``approve:<signal_id>`` or ``reject:<signal_id>``.
    """
    try:
        from telegram import Update
        upd: Update = update  # type: ignore
        query = upd.callback_query
        await query.answer()

        data = (query.data or "").strip()
        if ":" not in data:
            return

        action, signal_id = data.split(":", 1)
        signal = _pending_signals.pop(signal_id, None)

        if signal is None:
            await query.edit_message_text("⚠️ سیگنال یافت نشد (شاید منقضی شده).")
            return

        if action == "approve":
            await _execute_signal(signal)
            await query.edit_message_text(
                f"✅ سیگنال `{signal.get('symbol')}` تأیید و اجرا شد.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text(
                f"❌ سیگنال `{signal.get('symbol')}` رد شد.",
                parse_mode="Markdown",
            )

    except Exception as exc:
        logger.exception("[semi_auto] callback_signal_decision: %s", exc)


async def _execute_signal(signal: dict) -> None:
    """Forward an approved signal to the ExecutionService."""
    try:
        from backend.execution.execution_service import TradeSignal, execution_service
        ts = TradeSignal(
            symbol=signal.get("symbol", "EURUSD"),
            direction=signal.get("direction", "BUY"),
            volume=signal.get("volume", 0.01),
            entry=signal.get("entry_price"),
            sl=signal.get("sl_price"),
            tp=signal.get("tp_price"),
            confidence=signal.get("confidence", 0.0),
            strategy="semi_auto",
        )
        result = await execution_service.execute(ts)
        if not result.success:
            logger.error("[semi_auto] execution failed: %s", result.error)
    except Exception as exc:
        logger.exception("[semi_auto] _execute_signal: %s", exc)


def is_enabled() -> bool:
    """Return True if semi-auto mode is currently active."""
    return _semi_auto_enabled
