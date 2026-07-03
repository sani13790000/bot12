"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram handlers for AI intelligence and market analysis.

Commands
--------
/analyse <SYMBOL>   – run full SMC + PA analysis
/signal  <SYMBOL>   – get the current trade signal
/bias    <SYMBOL>   – market bias only (fast)
/intel              – multi-symbol intelligence summary

Every public function is registered on `router` so bot.py can
include it with  dp.include_router(intel_handler.router).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()

DEFAULT_SYMBOL    = "EURUSD"
DEFAULT_TIMEFRAME = "H1"
WATCH_SYMBOLS     = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]

_BIAS_EMOJI: dict[str, str] = {
    "BULLISH":  "🐂",
    "BEARISH":  "🔴",
    "NEUTRAL":  "⚪",
}


# ── Formatters ───────────────────────────────────────────────────── #

def _format_analysis(symbol: str, result: dict) -> str:
    """
    Render a full analysis result dict as Telegram Markdown.

    Expected keys: bias, structure_event, confidence, notes,
                   order_blocks (list), fvgs (list)
    """
    bias   = result.get("bias", "NEUTRAL")
    event  = result.get("structure_event", "NONE")
    conf   = result.get("confidence", 0.0) * 100
    notes  = result.get("notes", [])
    obs    = result.get("order_blocks", [])
    fvgs   = result.get("fvgs", [])

    bias_emoji = _BIAS_EMOJI.get(bias, "⚪")
    event_line = (
        f"\n🚨 *رویداد ساختار:* `{event}`"
        if event != "NONE" else ""
    )
    notes_text = ""
    if notes:
        bullet     = "\n".join(f"• {n}" for n in notes)
        notes_text = f"\n\n📝 *یادداشت‌ها:*\n{bullet}"

    return (
        f"🔭 *تحلیل SMC — {symbol}*\n\n"
        f"{bias_emoji} *تمایل:* `{bias}`{event_line}\n"
        f"🎯 *اطمینان:* `{conf:.0f}%`\n"
        f"📦 Order Blocks: `{len(obs)}`\n"
        f"⚡ FVGها: `{len(fvgs)}`"
        f"{notes_text}"
    )


def _format_signal(symbol: str, decision: dict) -> str:
    """Render a trade decision dict as Telegram Markdown."""
    direction = decision.get("direction", "NO_TRADE")
    reason    = decision.get("reason", "")
    conf      = decision.get("confidence", 0.0) * 100
    entry     = decision.get("entry_price")
    sl        = decision.get("sl_price")
    tp        = decision.get("tp_price")
    rr        = decision.get("risk_reward")

    dir_emoji = {
        "BUY":      "🐂 BUY",
        "SELL":     "🔴 SELL",
        "NO_TRADE": "⏸️ NO TRADE",
    }.get(direction, direction)

    lines = [
        f"⚡ *سیگنال — {symbol}*",
        "",
        f"🌀 *جهت:* {dir_emoji}",
        f"🎯 *اطمینان:* `{conf:.0f}%`",
        f"💬 *دلیل:* `{reason}`",
    ]
    if entry:
        lines.append(f"🔑 *ورودی:* `{entry:.5f}`")
    if sl:
        lines.append(f"🛑️ *SL:* `{sl:.5f}`")
    if tp:
        lines.append(f"🏁 *TP:* `{tp:.5f}`")
    if rr:
        lines.append(f"⚖️ *R:R:* `{rr:.2f}`")

    return "\n".join(lines)


def _format_intel_summary(results: dict[str, dict]) -> str:
    """Render a multi-symbol intelligence summary."""
    lines = ["📊 *خلاصه هوش بازار*\n"]
    for symbol, res in results.items():
        bias  = res.get("bias", "NEUTRAL")
        conf  = res.get("confidence", 0.0) * 100
        emoji = _BIAS_EMOJI.get(bias, "⚪")
        lines.append(f"{emoji} *{symbol}* — `{bias}` | `{conf:.0f}%`")
    return "\n".join(lines)


# ── Command handlers ─────────────────────────────────────────────── #

@router.message(Command("analyse"))
async def cmd_analyse(message: types.Message) -> None:
    """/analyse [SYMBOL] — Run a full SMC analysis."""
    args   = (message.text or "").split()[1:]
    symbol = args[0].upper() if args else DEFAULT_SYMBOL
    await message.answer(f"⏳ در حال تحلیل {symbol} ...")
    try:
        result = await _run_analysis(symbol)
        text   = _format_analysis(symbol, result)
        await message.answer(text, parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[intelligence] cmd_analyse %s: %s", symbol, exc)
        await message.answer(f"❌ خطا: {exc}")


@router.message(Command("signal"))
async def cmd_signal(message: types.Message) -> None:
    """/signal [SYMBOL] — Get current trade signal."""
    args   = (message.text or "").split()[1:]
    symbol = args[0].upper() if args else DEFAULT_SYMBOL
    await message.answer(f"⏳ در حال دریافت سیگنال {symbol} ...")
    try:
        decision = await _get_signal(symbol)
        text     = _format_signal(symbol, decision)
        await message.answer(text, parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[intelligence] cmd_signal %s: %s", symbol, exc)
        await message.answer(f"❌ {exc}")


@router.message(Command("bias"))
async def cmd_bias(message: types.Message) -> None:
    """/bias [SYMBOL] — Quick market bias check."""
    args   = (message.text or "").split()[1:]
    symbol = args[0].upper() if args else DEFAULT_SYMBOL
    try:
        result = await _run_analysis(symbol)
        bias   = result.get("bias", "NEUTRAL")
        conf   = result.get("confidence", 0.0) * 100
        emoji  = _BIAS_EMOJI.get(bias, "⚪")
        await message.answer(
            f"{emoji} *{symbol}* — تمایل: `{bias}` | اطمینان: `{conf:.0f}%`",
            parse_mode="Markdown",
        )
    except Exception as exc:
        logger.exception("[intelligence] cmd_bias %s: %s", symbol, exc)
        await message.answer(f"❌ {exc}")


@router.message(Command("intel"))
async def cmd_intel(message: types.Message) -> None:
    """/intel — Multi-symbol intelligence summary."""
    await message.answer("⏳ در حال تحلیل همه نمادها ...")
    try:
        results: dict[str, dict] = {}
        for symbol in WATCH_SYMBOLS:
            try:
                results[symbol] = await _run_analysis(symbol)
            except Exception as exc:
                logger.warning("[intelligence] intel %s failed: %s", symbol, exc)
                results[symbol] = {}
        text = _format_intel_summary(results)
        await message.answer(text, parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[intelligence] cmd_intel: %s", exc)
        await message.answer(f"❌ {exc}")


# ── Data-access helpers ───────────────────────────────────────────── #

async def _run_analysis(symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> dict:
    """
    Run SMC analysis for `symbol` and return a result dict.

    Production: candles from MT5 → SMCEngine.
    Fallback: neutral stub with warning note.
    """
    try:
        from backend.execution.mt5_connector import MT5Connector
        from backend.analysis.smc_engine import SMCEngine

        connector = MT5Connector()
        candles   = await connector.get_candles(symbol, timeframe, count=200)

        if candles:
            return SMCEngine().analyse(symbol, candles)

        logger.warning(
            "[intelligence] no candles for %s/%s — returning neutral",
            symbol, timeframe,
        )
        return {
            "bias": "NEUTRAL", "structure_event": "NONE",
            "confidence": 0.0,
            "notes": ["داده‌ای از MT5 دریافت نشد — اتصال را بررسی کنید"],
            "order_blocks": [], "fvgs": [],
        }

    except ImportError as exc:
        logger.warning("[intelligence] import error in _run_analysis: %s", exc)
        return {
            "bias": "NEUTRAL", "structure_event": "NONE",
            "confidence": 0.0,
            "notes": [f"وابستگی در دسترس نیست: {exc}"],
            "order_blocks": [], "fvgs": [],
        }
    except Exception as exc:
        logger.exception("[intelligence] _run_analysis %s failed: %s", symbol, exc)
        raise


async def _get_signal(symbol: str) -> dict:
    """
    Return the current decision-engine signal for `symbol`.

    Production: candles → SMCEngine → DecisionEngine → signal dict.
    Fallback: NO_TRADE with explanation.
    """
    try:
        from backend.execution.mt5_connector import MT5Connector
        from backend.analysis.smc_engine import SMCEngine
        from backend.analysis.decision_engine import DecisionEngine

        connector = MT5Connector()
        candles   = await connector.get_candles(symbol, DEFAULT_TIMEFRAME, count=200)

        if not candles:
            return {"direction": "NO_TRADE", "reason": "no_data", "confidence": 0.0}

        smc_result = SMCEngine().analyse(symbol, candles)
        return DecisionEngine().decide(symbol, smc_result, candles)

    except ImportError as exc:
        logger.warning("[intelligence] import error in _get_signal: %s", exc)
        return {"direction": "NO_TRADE", "reason": f"import_error: {exc}", "confidence": 0.0}
    except Exception as exc:
        logger.exception("[intelligence] _get_signal %s failed: %s", symbol, exc)
        raise
