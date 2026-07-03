"""
backend/telegram/handlers/intelligence.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram handlers for AI intelligence and market analysis.

Commands
--------
/analyse [SYMBOL]  -- Run full SMC analysis
/signal  [SYMBOL]  -- Get current trade signal
/bias    [SYMBOL]  -- Quick market bias check
/intel             -- Multi-symbol intelligence summary

FIX K-6: asyncio.wait_for(30s) + TimeoutError handler for all analysis commands.
"""
import asyncio
import logging
from typing import Optional

from aiogram import Router, types
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()

DEFAULT_SYMBOL    = "XAUUSD"
DEFAULT_TIMEFRAME  = "H1"
WATCH_SYMBOLS      = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100"]
ANALYSIS_TIMEOUT_S = 30.0

_BIAS_EMOJI = {"BULLISH": "😢", "BEARISH": "😣", "NEUTRAL": "⚪️"}


def _format_analysis(symbol: str, result: dict) -> str:
    bias        = result.get("bias", "NEUTRAL")
    structure   = result.get("structure_event", "NONE")
    conf        = result.get("confidence", 0.0) * 100
    notes       = result.get("notes", [])
    order_blocks = result.get("order_blocks", [])
    fvgs        = result.get("fvgs", [])
    emoji       = _BIAS_EMOJI.get(bias, "⚪️")

    lines = [
        f"{emoji} *{symbol} Analysis*",
        f"📈 *Bias:* `{bias}`",
        f"💥 *Structure:* `{structure}`",
        f"🎯 *Confidence:* `{conf:.0f}%`",
    ]
    if order_blocks:
        lines.append(f"📦 *Order Blocks:*�{len(order_blocks)})")
    if fvgs:
        lines.append(f"📥 *FVG3:* {len(fvgs)}")
    if notes:
        lines.append("\n📊Notes:")
        for note in notes[:3]:
            lines.append(f"  • {note}")
    return "\n".join(lines)


def _format_signal(symbol: str, decision: dict) -> str:
    direction = decision.get("direction", "NO_TRADE")
    reason    = decision.get("reason", "")
    conf      = decision.get("confidence", 0.0) * 100
    entry     = decision.get("entry")
    sl        = decision.get("sl")
    tp        = decision.get("tp")
    rr        = decision.get("rr_ratio")
    dir_emoji = {"BUY": "🙢", "SELL": "🙣", "NO_TRADE": "⚪ﻈ"}.get(direction, "⚪")
    lines = [
        f"📋 *{symbol} Signal*",
        f"🌀 *Direction:* {dir_emoji}",
        f"🎯 *Confidence:* `{conf:.0f}%`",
        f"💬 *Reason:* `{reason}`",
    ]
    if entry: lines.append(f"🔑 *Entry:* `{entry:.5f}`")
    if sl: lines.append(f"🛑️ *SL:* `{sl:.5f}`")
    if tp: lines.append(f"🏁 *TP:* `{tp:.5f}`")
    if rr: lines.append(f"⚖��� *R:R:* `{rr:.2f}`")
    return "\n".join(lines)


def _format_intel_summary(results: dict[str, dict]) -> str:
    lines = ["📊 *Multi-Symbol Intelligence*\n"]
    for symbol, res in results.items():
        bias  = res.get("bias", "NEUTRAL")
        conf  = res.get("confidence", 0.0) * 100
        emoji = _BIAS_EMOJI.get(bias, "⚪")
        lines.append(f"{e{moji} *{symbol}* — `{bias}` | `{conf:.0f}%`")
    return "\n".join(lines)


@router.message(Command("analyse"))
async def cmd_analyse(message: types.Message) -> None:
    args   = (message.text or "").split()[1:]
    symbol = args[0].upper() if args else DEFAULT_SYMBOL
    await message.answer(f"⏳ ادر حملت {symbol} ...")
    try:
        # FIX K-6: timeout 30s
        result = await asyncio.wait_for(_run_analysis(symbol), timeout=ANALYSIS_TIMEOUT_S)
        text   = _format_analysis(symbol, result)
        await message.answer(text, parse_mode="Markdown")
    except asyncio.TimeoutError:
        logger.warning("[intelligence] cmd_analyse %s: timeout", symbol)
        await message.answer(f"␱ \u0632\u0645\u0646P `{symbol}` \u062e\u062a\u0645 \u064a\u0627\u0641\u062a.", parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[intelligence] cmd_analyse %s: %s", symbol, exc)
        await message.answer(f"❌ \u062f\u0639\u0646: `{type(exc).__name__}`", parse_mode="Markdown")


@router.message(Command("signal"))
async def cmd_signal(message: types.Message) -> None:
    args   = (message.text or "").split()[1:]
    symbol = args[0].upper() if args else DEFAULT_SYMBOL
    await message.answer(f"⏳ در حال {symbol} ...")
    try:
        # FIX K-6: timeout 30s
        decision = await asyncio.wait_for(_get_signal(symbol), timeout=ANALYSIS_TIMEOUT_S)
        text     = _format_signal(symbol, decision)
        await message.answer(text, parse_mode="Markdown")
    except asyncio.TimeoutError:
        logger.warning("[intelligence] cmd_signal %s: timeout", symbol)
        await message.answer(f"␱ timeout baraye `{symbol}`.", parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[intelligence] cmd_signal %s: %s", symbol, exc)
        await message.answer(f"❌ {type(exc).__name__}", parse_mode="Markdown")


@router.message(Command("bias"))
async def cmd_bias(message: types.Message) -> None:
    args   = (message.text or "").split()[1:]
    symbol = args[0].upper() if args else DEFAULT_SYMBOL
    try:
        result = await asyncio.wait_for(_run_analysis(symbol), timeout=ANALYSIS_TIMEOUT_S)
        bias   = result.get("bias", "NEUTRAL")
        conf   = result.get("confidence", 0.0) * 100
        emoji  = _BIAS_EMOJI.get(bias, "⚪")
        await message.answer(f"{emoji} *{symbol}* - `o{bias}` | `{conf:.0f}%`", parse_mode="Markdown")
    except asyncio.TimeoutError:
        await message.answer(f"␱ timeout for `{symbol}`.")
    except Exception as exc:
        logger.exception("[intelligence] cmd_bias %s: %s", symbol, exc)
        await message.answer(f"❌ {type(exc).__name__}")


@router.message(Command("intel"))
async def cmd_intel(message: types.Message) -> None:
    await message.answer("Intel scanning all symbols...")
    try:
        results: dict[str, dict] = {}
        for symbol in WATCH_SYMBOLS:
            try:
                results[symbol] = await asyncio.wait_for(_run_analysis(symbol), timeout=ANALYSIS_TIMEOUT_S)
            except Exception as exc:
                logger.warning("[intelligence] intel %s: %s", symbol, exc)
                results[symbol] = {}
        text = _format_intel_summary(results)
        await message.answer(text, parse_mode="Markdown")
    except Exception as exc:
        logger.exception("[intelligence] cmd_intel: %s", exc)
        await message.answer(f"❌ {exc}")


async def _run_analysis(symbol: str, timeframe: str = DEFAULT_TIMEFRAME) -> dict:
    """Run SMC analysis and return result dict."""
    try:
        from backend.execution.mt5_connector import MT5Connector
        from backend.analysis.smc_engine import SMCEngine
        connector = MT5Connector()
        candles   = await connector.get_candles(symbol, timeframe, count=200)
        if candles:
            return SMCEngine().analyse(symbol, candles)
        logger.warning("[intelligence] no candles for %s/%s", symbol, timeframe)
        return {"bias": "NEUTRAL", "structure_event": "NONE", "confidence": 0.0, "notes": ["no data"], "order_blocks": [], "fvgs": []}
    except ImportError as exc:
        logger.warning("[intelligence] import error: %s", exc)
        return {"bias": "NEUTRAL", "structure_event": "NONE", "confidence": 0.0, "notes": [f"import_error: {exc}"], "order_blocks": [], "fvgs": []}
    except Exception as exc:
        logger.exception("[intelligence] _run_analysis %s failed: %s", symbol, exc)
        raise


async def _get_signal(symbol: str) -> dict:
    """Get decision-engine signal for symbol."""
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
