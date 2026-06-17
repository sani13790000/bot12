#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
فایل: backend/telegram/handlers/reports.py
توضیح: سیستم گزارش‌دهی کامل تلگرام
شامل: گزارش روزانه، هفتگی، ماهانه، وین‌ریت، سود/ضرر، تاریخچه معاملات
تمام پیام‌ها به فارسی
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.markdown import hbold, hcode
from datetime import datetime, timedelta
from typing import Optional
import logging

from ..rbac import require_permission, Permission
from ...database.connection import get_db
from ...services.trade_service import TradeService
from ...core.logger import get_logger

logger = get_logger(__name__)
router = Router(name="reports")


def _format_number(value: float, decimals: int = 2) -> str:
    """فرمت‌بندی عدد با جداکننده هزارگان"""
    return f"{value:,.{decimals}f}"


def _format_pnl(value: float) -> str:
    """فرمت‌بندی سود/ضرر با رنگ (ایموجی)"""
    if value > 0:
        return f"✅ +{_format_number(value)}"
    elif value < 0:
        return f"❌ {_format_number(value)}"
    return f"➖ {_format_number(value)}"


def _format_trade_row(trade: dict) -> str:
    """فرمت‌بندی یک ردیف معامله"""
    direction = "📈 خرید" if trade.get("direction") == "buy" else "📉 فروش"
    result    = _format_pnl(trade.get("profit", 0))
    symbol    = trade.get("symbol", "---")
    open_time = trade.get("open_time", "")
    if isinstance(open_time, datetime):
        open_time = open_time.strftime("%m/%d %H:%M")
    return f"  {direction} {symbol} | {result} | {open_time}"


async def _get_report_data(db, start_date: datetime, end_date: datetime) -> dict:
    """دریافت داده‌های گزارش از دیتابیس"""
    try:
        service = TradeService(db)
        trades = await service.get_trades_in_range(start_date, end_date)

        total_trades  = len(trades)
        wins          = [t for t in trades if t.get("profit", 0) > 0]
        losses        = [t for t in trades if t.get("profit", 0) < 0]
        breakeven     = [t for t in trades if t.get("profit", 0) == 0]
        total_profit  = sum(t.get("profit", 0) for t in wins)
        total_loss    = abs(sum(t.get("profit", 0) for t in losses))
        net_profit    = total_profit - total_loss
        win_rate      = (len(wins) / total_trades * 100) if total_trades > 0 else 0
        avg_win       = (total_profit / len(wins)) if wins else 0
        avg_loss      = (total_loss   / len(losses)) if losses else 0
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float("inf")
        best_trade    = max(trades, key=lambda t: t.get("profit", 0), default={})
        worst_trade   = min(trades, key=lambda t: t.get("profit", 0), default={})

        return {
            "total_trades":  total_trades,
            "wins":          len(wins),
            "losses":        len(losses),
            "breakeven":     len(breakeven),
            "win_rate":      win_rate,
            "total_profit":  total_profit,
            "total_loss":    total_loss,
            "net_profit":    net_profit,
            "avg_win":       avg_win,
            "avg_loss":      avg_loss,
            "profit_factor": profit_factor,
            "best_trade":    best_trade.get("profit", 0),
            "worst_trade":   worst_trade.get("profit", 0),
            "trades":        trades,
        }
    except Exception as e:
        logger.error(f"خطا در دریافت داده گزارش: {e}")
        return {}


def _build_report_message(data: dict, title: str, period: str) -> str:
    """ساخت پیام گزارش"""
    if not data:
        return f"❌ خطا در دریافت اطلاعات گزارش {title}"

    pf_str = (f"{data['profit_factor']:.2f}"
              if data["profit_factor"] != float("inf") else "∞")

    # رنگ امتیاز وین‌ریت
    wr = data["win_rate"]
    wr_emoji = "🟢" if wr >= 60 else ("🟡" if wr >= 50 else "🔴")

    msg = (
        f"📊 {hbold(title)}
"
        f"📅 دوره: {period}
"
        f"{'─'*30}
"
        f"📈 {hbold('خلاصه معاملات')}
"
        f"  کل معاملات:   {data['total_trades']}
"
        f"  برنده:         ✅ {data['wins']}
"
        f"  بازنده:        ❌ {data['losses']}
"
        f"  سربه‌سر:       ➖ {data['breakeven']}
"
        f"  {wr_emoji} وین‌ریت:       {wr:.1f}%
"
        f"{'─'*30}
"
        f"💰 {hbold('نتایج مالی')}
"
        f"  سود کل:        {_format_pnl(data['total_profit'])}
"
        f"  ضرر کل:        ❌ -{_format_number(data['total_loss'])}
"
        f"  سود/ضرر خالص: {_format_pnl(data['net_profit'])}
"
        f"{'─'*30}
"
        f"📉 {hbold('آمار پیشرفته')}
"
        f"  میانگین برد:  +{_format_number(data['avg_win'])}
"
        f"  میانگین باخت: -{_format_number(data['avg_loss'])}
"
        f"  Profit Factor: {pf_str}
"
        f"  بهترین معامله: {_format_pnl(data['best_trade'])}
"
        f"  بدترین معامله: {_format_pnl(data['worst_trade'])}
"
    )
    return msg


# ===== دستورات گزارش =====

@router.message(Command("report_daily"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_daily_report(message: Message):
    """گزارش روزانه"""
    await message.answer("⏳ در حال آماده‌سازی گزارش روزانه...")
    try:
        async with get_db() as db:
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            data  = await _get_report_data(db, today, datetime.now())
            period = today.strftime("%Y/%m/%d")
            msg   = _build_report_message(data, "گزارش روزانه", period)
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش روزانه: {e}")
        await message.answer("❌ خطا در دریافت گزارش روزانه")


@router.message(Command("report_weekly"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_weekly_report(message: Message):
    """گزارش هفتگی"""
    await message.answer("⏳ در حال آماده‌سازی گزارش هفتگی...")
    try:
        async with get_db() as db:
            end   = datetime.now()
            start = end - timedelta(days=7)
            data  = await _get_report_data(db, start, end)
            period = f"{start.strftime('%Y/%m/%d')} تا {end.strftime('%Y/%m/%d')}"
            msg   = _build_report_message(data, "گزارش هفتگی", period)
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش هفتگی: {e}")
        await message.answer("❌ خطا در دریافت گزارش هفتگی")


@router.message(Command("report_monthly"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_monthly_report(message: Message):
    """گزارش ماهانه"""
    await message.answer("⏳ در حال آماده‌سازی گزارش ماهانه...")
    try:
        async with get_db() as db:
            end   = datetime.now()
            start = end - timedelta(days=30)
            data  = await _get_report_data(db, start, end)
            period = f"{start.strftime('%Y/%m/%d')} تا {end.strftime('%Y/%m/%d')}"
            msg   = _build_report_message(data, "گزارش ماهانه", period)
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش ماهانه: {e}")
        await message.answer("❌ خطا در دریافت گزارش ماهانه")


@router.message(Command("report_winrate"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_winrate_report(message: Message):
    """گزارش وین‌ریت"""
    try:
        async with get_db() as db:
            # مقایسه دوره‌های مختلف
            now    = datetime.now()
            today  = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week   = now - timedelta(days=7)
            month  = now - timedelta(days=30)

            d_day   = await _get_report_data(db, today, now)
            d_week  = await _get_report_data(db, week,  now)
            d_month = await _get_report_data(db, month, now)

            msg = (
                f"🎯 {hbold('گزارش وین‌ریت')}
"
                f"{'─'*30}
"
                f"📅 امروز:       {d_day.get('win_rate', 0):.1f}% "
                f"({d_day.get('wins', 0)}/{d_day.get('total_trades', 0)})
"
                f"📅 این هفته:   {d_week.get('win_rate', 0):.1f}% "
                f"({d_week.get('wins', 0)}/{d_week.get('total_trades', 0)})
"
                f"📅 این ماه:    {d_month.get('win_rate', 0):.1f}% "
                f"({d_month.get('wins', 0)}/{d_month.get('total_trades', 0)})
"
                f"{'─'*30}
"
                f"💰 سود خالص این ماه: {_format_pnl(d_month.get('net_profit', 0))}
"
                f"📊 Profit Factor:     "
                f"{d_month.get('profit_factor', 0):.2f}"
            )
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش وین‌ریت: {e}")
        await message.answer("❌ خطا در دریافت گزارش وین‌ریت")


@router.message(Command("report_profit"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_profit_report(message: Message):
    """گزارش سود"""
    try:
        async with get_db() as db:
            now   = datetime.now()
            month = now - timedelta(days=30)
            data  = await _get_report_data(db, month, now)
            winning_trades = [t for t in data.get("trades", []) if t.get("profit", 0) > 0]
            top5 = sorted(winning_trades, key=lambda t: t.get("profit", 0), reverse=True)[:5]

            msg = (
                f"✅ {hbold('گزارش سود (۳۰ روز اخیر)')}
"
                f"{'─'*30}
"
                f"سود کل:       +{_format_number(data.get('total_profit', 0))}
"
                f"تعداد معاملات: {data.get('wins', 0)}
"
                f"میانگین سود:  +{_format_number(data.get('avg_win', 0))}
"
                f"بهترین معامله: +{_format_number(data.get('best_trade', 0))}
"
                f"{'─'*30}
"
                f"🏆 {hbold('۵ معامله برتر')}
"
            )
            for t in top5:
                msg += _format_trade_row(t) + "
"
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش سود: {e}")
        await message.answer("❌ خطا در دریافت گزارش سود")


@router.message(Command("report_loss"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_loss_report(message: Message):
    """گزارش ضرر"""
    try:
        async with get_db() as db:
            now   = datetime.now()
            month = now - timedelta(days=30)
            data  = await _get_report_data(db, month, now)
            losing_trades = [t for t in data.get("trades", []) if t.get("profit", 0) < 0]
            worst5 = sorted(losing_trades, key=lambda t: t.get("profit", 0))[:5]

            msg = (
                f"❌ {hbold('گزارش ضرر (۳۰ روز اخیر)')}
"
                f"{'─'*30}
"
                f"ضرر کل:        -{_format_number(data.get('total_loss', 0))}
"
                f"تعداد معاملات: {data.get('losses', 0)}
"
                f"میانگین ضرر:   -{_format_number(data.get('avg_loss', 0))}
"
                f"بدترین معامله: {_format_pnl(data.get('worst_trade', 0))}
"
                f"{'─'*30}
"
                f"⚠️ {hbold('۵ بدترین معامله')}
"
            )
            for t in worst5:
                msg += _format_trade_row(t) + "
"
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش ضرر: {e}")
        await message.answer("❌ خطا در دریافت گزارش ضرر")


@router.message(Command("report_trades"))
@require_permission(Permission.VIEW_REPORTS)
async def cmd_trades_report(message: Message):
    """گزارش معاملات (۲۴ ساعت اخیر)"""
    try:
        async with get_db() as db:
            start = datetime.now() - timedelta(hours=24)
            data  = await _get_report_data(db, start, datetime.now())
            trades = data.get("trades", [])[:10]

            msg = (
                f"📋 {hbold('معاملات ۲۴ ساعت اخیر')}
"
                f"{'─'*30}
"
                f"تعداد: {data.get('total_trades', 0)} | "
                f"وین‌ریت: {data.get('win_rate', 0):.1f}%
"
                f"سود/ضرر: {_format_pnl(data.get('net_profit', 0))}
"
                f"{'─'*30}
"
            )
            if not trades:
                msg += "هیچ معامله‌ای در این بازه ثبت نشده است.
"
            else:
                for t in trades:
                    msg += _format_trade_row(t) + "
"
            await message.answer(msg, parse_mode="HTML")
    except Exception as e:
        logger.error(f"خطا در گزارش معاملات: {e}")
        await message.answer("❌ خطا در دریافت معاملات")
