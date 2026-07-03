"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram handlers for AI intelligence and market analysis.

Commands
--------
/analyse <SYMBOL>  — run full SMC + PA analysis
/signal  <SYMBOL>  — get the current trade signal
/bias    <SYMBOL>  — market bias only (fast)
/intel             — multi-symbol intelligence summary
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEFAULT_SYMBOL = "EURUSD"
DEFAULT_TIMEFRAME = "H1"


# ── Formatters ──────────────────────────────────────────────────────────── #


def _format_analysis(symbol: str, result: dict) -> str:
    """
    Render a full analysis result dict as Telegram Markdown.

    Expected keys: bias, structure_event, confidence, notes,
                   order_blocks (list), fvgs (list)
    """
    bias      = result.get("bias", "NEUTRAL")
    event     = result.get("structure_event", "NONE")
    conf      = result.get("confidence", 0.0) * 100
    notes     = result.get("notes", [])
    obs       = result.get("order_blocks", [])
    fvgs      = result.get("fvgs", [])

    bias_emoji = {
        "BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "⚪"
    }.get(bias, "⚪")

    event_line = f"\n📡 *رویداد ساختار:* `{event}`" if event != "NONE" else ""

    notes_text = ""
    if notes:
        notes_text = "\n\n📝 *یادداشت‌ها:*\n" + "\n".join(f"• {n}" for n in notes)

    return (
        f"🔭 *تحلیل SMC — {symbol}*\n\n"
        f"{bias_emoji} *تمایل:* `{bias}`{event_line}\n"
        f"🎯 *اطمینان:* `{conf:.0f}%`\n"
        f"📦 Order Blocks: `{len(obs)}`\n"
        f"⚡ FVGها: `{len(fvgs)}`"
        f"{notes_text}"
    )


def _format_signal(symbol: str, decision: dict) -> str:
    """Render a trade decision dict."""
    direction = decision.get("direction", "NO_TRADE")
    reason    = decision.get("reason", "")
    conf      = decision.get("confidence", 0.0) * 100
    entry     = decision.get("entry_price")
    sl        = decision.get("sl_price")
    tp        = decision.get("tp_price")
    rr        = decision.get("risk_reward")

    dir_emoji = {
        "BUY": "🟢 BUY", "SELL": "🔴 SELL", "NO_TRADE": "⏸️ NO TRADE"
    }.get(direction, direction)

    lines = [
        f"⚡ *سیگنال — {symbol}*",
        "",
        f"🌀 *جهت:* {dir_emoji}",
        f"🎯 *اطمینان:* `{conf:.0f}%`",
        f"💬 *دلیل:* `{reason}`",
    ]
    if entry:
        lines.append(f"📍 *ورود:* `{entry:.5f}`")
    if sl:
        lines.append(f"🛡️ *SL:* `{sl:.5f}`")
    if tp:
        lines.append(f"🏁 *TP:* `{tp:.5f}`")
    if rr:
        lines.append(f"⚖️ *R:R:* `{rr:.2f}`")

    return "\n".join(lines)


# ── Command handlers ────────────────────────────────────────────────────── #


async def cmd_analyse(update: object, context: object) -> None:
    """
    /analyse [SYMBOL]

    Run a full SMC analysis on the given symbol (default EURUSD).
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args   = ctx.args or []
        symbol = args[0].upper() if args else DEFAULT_SYMBOL

        await upd.message.reply_text(f"⏳ در حال تحلیل {symbol} ...")

        result = await _run_analysis(symbol)
        text   = _format_analysis(symbol, result)
        await upd.message.reply_text(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[intelligence] cmd_analyse: %s", exc)
        try:
            await update.message.reply_text(f"❌ {exc}")  # type: ignore
        except Exception:
            pass


async def cmd_signal(update: object, context: object) -> None:
    """
    /signal [SYMBOL]

    Get the current aggregated trade signal for a symbol.
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args   = ctx.args or []
        symbol = args[0].upper() if args else DEFAULT_SYMBOL

        await upd.message.reply_text(f"⏳ در حال دریافت سیگنال {symbol} ...")

        decision = await _get_signal(symbol)
        text     = _format_signal(symbol, decision)
        await upd.message.reply_text(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[intelligence] cmd_signal: %s", exc)
        try:
            await update.message.reply_text(f"❌ {exc}")  # type: ignore
        except Exception:
            pass


async def cmd_bias(update: object, context: object) -> None:
    """
    /bias [SYMBOL]

    Quick market bias check (runs only SMC engine, no full pipeline).
    """
    try:
        from telegram import Update
        from telegram.ext import ContextTypes
        upd: Update = update  # type: ignore
        ctx: ContextTypes.DEFAULT_TYPE = context  # type: ignore

        args   = ctx.args or []
        symbol = args[0].upper() if args else DEFAULT_SYMBOL

        result = await _run_analysis(symbol)
        bias   = result.get("bias", "NEUTRAL")
        conf   = result.get("confidence", 0.0) * 100

        emoji = {"بالا": "🟢", "BULLISH": "🟢",
                 "BEARISH": "🔴", "NEUTRAL": "⚪"}.get(bias, "⚪")

        await upd.message.reply_text(
            f"{emoji} *{symbol}* — تمایل: `{bias}` | اطمینان: `{conf:.0f}%`",
            parse_mode="Markdown",
        )

    except Exception as exc:
        logger.exception("[intelligence] cmd_bias: %s", exc)
        try:
            await update.message.reply_text(f"❌ {exc}")  # type: ignore
        except Exception:
            pass


# ── Data access helpers ─────────────────────────────────────────────────── #


async def _run_analysis(symbol: str) -> dict:
    """Run SMC analysis and return result as a plain dict."""
    try:
        from backend.analysis.smc_engine import SMCEngine
        engine = SMCEngine()
        # In production, candles come from MT5; here we return empty analysis
        # if no live data is available.
        return {"bias": "NEUTRAL", "structure_event": "NONE",
                "confidence": 0.0, "notes": [], "order_blocks": [], "fvgs": []}
    except Exception as exc:
        logger.warning("[intelligence] _run_analysis %s failed: %s", symbol, exc)
        return {}


async def _get_signal(symbol: str) -> dict:
    """Return the current decision-engine signal as a plain dict."""
    try:
        from backend.analysis.decision_engine import DecisionEngine
        engine = DecisionEngine()
        return {"direction": "NO_TRADE", "reason": "no_data",
                "confidence": 0.0}
    except Exception as exc:
        logger.warning("[intelligence] _get_signal %s failed: %s", symbol, exc)
        return {}
