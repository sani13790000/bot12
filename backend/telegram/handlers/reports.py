"""
backend/telegram/handlers/reports.py
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Telegram handlers for performance reports.

Commands
--------
/report daily    – today's P&L summary
/report weekly   – last 7 days
/report monthly  – last 30 days
/report all      – all-time stats
"""
from __future__ import annotations

import logging

from aiogram import Router, types
from aiogram.filters import Command

logger = logging.getLogger(__name__)
router = Router()

PERIOD_DAYS: dict[str, int] = {
    "daily":   1,
    "weekly":  7,
    "monthly": 30,
    "all":     0,
}


# ── Formatter ────────────────────────────────────────────────────── #

def _format_report(stats: dict, period: str) -> str:
    """
    Render a performance stats dict as Telegram Markdown.

    Expected keys (all optional, default to zero):
        total_trades, winning_trades, losing_trades, win_rate,
        net_pnl, gross_pnl, max_drawdown, avg_rr,
        best_trade, worst_trade
    """
    period_label = period.upper()
    total  = stats.get("total_trades", 0)
    wins   = stats.get("winning_trades", 0)
    losses = stats.get("losing_trades", 0)
    wr     = stats.get("win_rate", 0.0) * 100
    net    = stats.get("net_pnl", 0.0)
    gross  = stats.get("gross_pnl", 0.0)
    dd     = stats.get("max_drawdown", 0.0) * 100
    rr     = stats.get("avg_rr", 0.0)
    best   = stats.get("best_trade", 0.0)
    worst  = stats.get("worst_trade", 0.0)
    sign   = "💰" if net >= 0 else "💸"

    return (
        f"📊 *گزارش عملکرد — {period_label}*\n\n"
        f"📈 تعداد معاملات: `{total}` "
        f"(برد: `{wins}` | باخت: `{losses}`)\n"
        f"🎯 نرخ برد:        `{wr:.1f}%`\n"
        f"{sign} سود/زیان خالص:  `{net:+.2f}` USD\n"
        f"💰 سود ناخالص:      `{gross:+.2f}` USD\n"
        f"📉 حداکثر Drawdown: `{dd:.1f}%`\n"
        f"⚖️ میانگین R:R:      `{rr:.2f}`\n"
        f"🔥 بهترین معامله:   `{best:+.2f}` USD\n"
        f"🔻 بدترین معامله:  `{worst:+.2f}` USD"
    )


# ── Command handlers ─────────────────────────────────────────────── #

@router.message(Command("report"))
async def cmd_report(message: types.Message) -> None:
    """
    /report [daily|weekly|monthly|all]

    Defaults to daily when no argument is given.
    """
    try:
        args   = (message.text or "").split()[1:]
        period = args[0].lower() if args else "daily"

        if period not in PERIOD_DAYS:
            await message.answer(
                "⚠️ دوره معتبر نیست.\n"
                "*گزینه‌ها:* daily | weekly | monthly | all",
                parse_mode="Markdown",
            )
            return

        await message.answer("⏳ در حال دریافت گزارش ...")

        days  = PERIOD_DAYS[period]
        stats = await _fetch_stats(days)
        text  = _format_report(stats, period)
        await message.answer(text, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("[reports] cmd_report: %s", exc)
        try:
            await message.answer(f"❌ خطا: {exc}")
        except Exception:
            pass


# ── Data access ──────────────────────────────────────────────────── #

async def _fetch_stats(days: int) -> dict:
    """Fetch aggregated performance stats from the analytics service."""
    try:
        from backend.analytics.analytics_service import analytics_service
        return await analytics_service.get_performance_stats(days=days)
    except Exception as exc:
        logger.warning("[reports] _fetch_stats(%d) failed: %s", days, exc)
        return {}
