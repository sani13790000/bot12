"""
backend/telegram/handlers/reports.py
Galaxy Vast AI — Telegram Report Handlers

Commands:
  /daily_report    — daily performance summary
  /weekly_report   — weekly performance summary
  /monthly_report  — monthly summary
  /trade_history   — recent trade list
  /pnl_chart       — equity curve snapshot
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _format_header(title: str, period: str) -> str:
    return (
        f"\U0001f4ca <b>{title}</b>\n"
        f"\U0001f4c5 \u062f\u0648\u0631\u0647: {period}\n"
        "\u2500" * 20 + "\n"
    )


async def cmd_daily_report(message: Any, stats: Dict) -> None:
    """Send daily performance report."""
    total = stats.get("total_trades", 0)
    wins = stats.get("winning_trades", 0)
    pnl = stats.get("total_pnl", 0.0)
    wr = (wins / total * 100) if total else 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = _format_header("\u06af\u0632\u0627\u0631\u0634 \u0631\u0648\u0632\u0627\u0646\u0647", today)
    body = (
        f"\U0001f4b9 \u0645\u0639\u0627\u0645\u0644\u0627\u062a: {total}\n"
        f"\U0001f3af \u0648\u06cc\u0646\u200c\u0631\u06cc\u062a: {wr:.1f}%\n"
        f"\U0001f4b0 \u0633\u0648\u062f/\u0632\u06cc\u0627\u0646: ${pnl:+.2f}"
    )
    try:
        await message.answer(header + body, parse_mode="HTML")
    except Exception as exc:
        logger.error("daily_report: %s", exc)


async def cmd_weekly_report(message: Any, stats: Dict) -> None:
    """Send weekly performance report."""
    total = stats.get("total_trades", 0)
    wins = stats.get("winning_trades", 0)
    pnl = stats.get("total_pnl", 0.0)
    wr = (wins / total * 100) if total else 0.0
    header = _format_header("\u06af\u0632\u0627\u0631\u0634 \u0647\u0641\u062a\u06af\u06cc", "7 \u0631\u0648\u0632 \u06af\u0630\u0634\u062a\u0647")
    body = (
        f"\U0001f4b9 \u0645\u0639\u0627\u0645\u0644\u0627\u062a: {total}\n"
        f"\U0001f3af \u0648\u06cc\u0646\u200c\u0631\u06cc\u062a: {wr:.1f}%\n"
        f"\U0001f4b0 \u0633\u0648\u062f/\u0632\u06cc\u0627\u0646: ${pnl:+.2f}"
    )
    try:
        await message.answer(header + body, parse_mode="HTML")
    except Exception as exc:
        logger.error("weekly_report: %s", exc)


async def cmd_trade_history(message: Any, trades: List[Dict]) -> None:
    """Send recent trade history."""
    if not trades:
        try:
            await message.answer("\U0001f4cb \u0647\u06cc\u0686 \u0645\u0639\u0627\u0645\u0644\u0647\u200c\u0627\u06cc \u06cc\u0627\u0641\u062a \u0646\u0634\u062f", parse_mode="HTML")
        except Exception:
            pass
        return
    lines = ["\U0001f4cb <b>\u062a\u0627\u0631\u06cc\u062e\u0686\u0647 \u0645\u0639\u0627\u0645\u0644\u0627\u062a</b>\n"]
    for t in trades[-10:]:
        icon = "\u2705" if t.get("profitable") else "\u274c"
        sym = t.get("symbol", "?")
        pnl = t.get("pnl", 0.0)
        lines.append(f"{icon} {sym}: ${pnl:+.2f}")
    try:
        await message.answer("\n".join(lines), parse_mode="HTML")
    except Exception as exc:
        logger.error("trade_history: %s", exc)


async def cmd_pnl_chart(message: Any, equity_curve: List[float]) -> None:
    """Send text-based equity curve chart."""
    if not equity_curve:
        try:
            await message.answer("\U0001f4c9 \u062f\u0627\u062f\u0647\u200c\u0627\u06cc \u06a9\u0627\f\u06cc \u0646\u06cc\u0633\u062a")
        except Exception:
            pass
        return
    mn = min(equity_curve); mx = max(equity_curve)
    rng = mx - mn or 1
    bars = []
    for v in equity_curve[-20:]:
        h = int((v - mn) / rng * 8)
        bars.append("\u2588" * max(1, h))
    chart = "\n".join(bars)
    try:
        await message.answer(f"<pre>\n{chart}\n</pre>", parse_mode="HTML")
    except Exception as exc:
        logger.error("pnl_chart: %s", exc)
