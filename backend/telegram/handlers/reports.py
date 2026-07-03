"""
backend/telegram/handlers/reports.py
Galaxy Vast AI - Report Telegram Handlers

Reports: daily, weekly, monthly, win-rate, P&L, trade history
All messages in Persian (Farsi)
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.formatting import hbold

logger = logging.getLogger(__name__)
router = Router()


def _format_report(title: str, period: str, data: Dict[str, Any]) -> str:
    wr    = data["win_rate"]
    pnl   = data["net_pnl"]
    sign  = "+" if pnl >= 0 else ""
    wr_em = "🟢" if wr >= 60 else ("🟡" if wr >= 50 else "🔴")
    lines = [
        f"📊 {hbold(title)}",
        f"📅 دوره: {period}",
        f"{"—" * 30}",
        f"📈 کل معاملات: {data['total_trades']}",
        f"✅ برنده: {data['wins']}",
        f"❌ بازنده: {data['losses']}",
        f"{wr_em} وین ریت: {wr:.1f}%",
        f"💵 سود/ضرر خالص: {sign}{pnl:.2f}$",
        f"💰 بهترین معامله: {data.get('best_trade', 'N/A')}",
        f"📉 بدترین معامله: {data.get('worst_trade', 'N/A')}",
    ]
    return "\n".join(lines)


@router.message(Command("daily_report"))
async def cmd_daily_report(message: Message) -> None:
    """Show daily trading report."""
    try:
        from backend.analytics.report_generator import ReportGenerator
        data = await ReportGenerator().get_daily_report()
        text = _format_report("گزارش روزانه", "امروز", data)
        await message.answer(text, parse_mode="HTML")
    except Exception as exc:
        logger.error("daily_report error: %s", exc)
        await message.answer(f"خطا در دریافت گزارش: {exc}")


@router.message(Command("weekly_report"))
async def cmd_weekly_report(message: Message) -> None:
    """Show weekly trading report."""
    try:
        from backend.analytics.report_generator import ReportGenerator
        data = await ReportGenerator().get_weekly_report()
        text = _format_report("گزارش هفتگی", "هفته جاری", data)
        await message.answer(text, parse_mode="HTML")
    except Exception as exc:
        logger.error("weekly_report error: %s", exc)
        await message.answer(f"خطا: {exc}")


@router.message(Command("monthly_report"))
async def cmd_monthly_report(message: Message) -> None:
    """Show monthly trading report."""
    try:
        from backend.analytics.report_generator import ReportGenerator
        data = await ReportGenerator().get_monthly_report()
        text = _format_report("گزارش ماهانه", "ماه جاری", data)
        await message.answer(text, parse_mode="HTML")
    except Exception as exc:
        logger.error("monthly_report error: %s", exc)
        await message.answer(f"خطا: {exc}")


@router.message(Command("trade_history"))
async def cmd_trade_history(message: Message) -> None:
    """Show last 10 trades."""
    try:
        from backend.services.trade_service import TradeService
        trades = await TradeService().get_recent_trades(limit=10)
        if not trades:
            await message.answer("هیچ معامله‌ای یافت نشد")
            return
        lines = ["📜 *تاریخچه معاملات*"]
        for t in trades:
            sign = "+" if t["pnl"] >= 0 else ""
            icon = "✅" if t["pnl"] >= 0 else "❌"
            lines.append(f"{icon} {t['symbol']} {t['direction']} {sign}{t['pnl']:.2f}$")
        await message.answer("\n".join(lines), parse_mode="Markdown")
    except Exception as exc:
        logger.error("trade_history error: %s", exc)
        await message.answer(f"خطا: {exc}")
