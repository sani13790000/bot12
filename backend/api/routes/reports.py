"""
روت‌های گزارش‌ها

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime, timedelta

from ...core.logger import get_logger
from ...database import db
from .auth import get_current_user

logger = get_logger("api.reports")
router = APIRouter()


@router.get("/daily")
async def daily_report(
    date: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """
    گزارش روزانه

    شامل:
    - تعداد معاملات
    - وین ریت
    - سود/ضرر
    - آمار سیگنال‌ها
    """
    if date:
        report_date = datetime.fromisoformat(date).date()
    else:
        report_date = datetime.utcnow().date()

    # دریافت آمار
    stats = await db.select_one("daily_statistics", {
        "user_id": user["id"],
        "stat_date": report_date.isoformat()
    })

    # دریافت معاملات روز
    next_day = report_date + timedelta(days=1)
    trades = await db.select_many(
        "trades",
        filters={
            "user_id": user["id"],
            "status": "closed"
        },
        limit=100
    )

    # محاسبه اگر آمار ذخیره نشده
    if not stats:
        total = len(trades)
        winning = len([t for t in trades if t.get("profit_money", 0) > 0])
        losing = len([t for t in trades if t.get("profit_money", 0) < 0])

        stats = {
            "total_trades": total,
            "winning_trades": winning,
            "losing_trades": losing,
            "win_rate": (winning / total * 100) if total > 0 else 0,
            "gross_profit": sum(t.get("profit_money", 0) for t in trades if t.get("profit_money", 0) > 0),
            "gross_loss": sum(t.get("profit_money", 0) for t in trades if t.get("profit_money", 0) < 0),
            "net_profit": sum(t.get("profit_money", 0) or 0 for t in trades)
        }

    return {
        "success": True,
        "data": {
            "date": report_date.isoformat(),
            "summary": stats,
            "trades": trades[:20]  # 20 معامله اخیر
        }
    }


@router.get("/weekly")
async def weekly_report(user: dict = Depends(get_current_user)):
    """
    گزارش هفتگی

    شامل:
    - خلاصه هفته
    - تفکیک روزانه
    - بهترین/بدترین روز
    """
    today = datetime.utcnow().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    total_trades = 0
    total_profit = 0
    winning = 0
    losing = 0
    gross_profit = 0
    gross_loss = 0
    daily_breakdown = []

    for i in range(7):
        day = week_start + timedelta(days=i)
        stats = await db.select_one("daily_statistics", {
            "user_id": user["id"],
            "stat_date": day.isoformat()
        })

        if stats:
            daily_breakdown.append({
                "date": day.isoformat(),
                "trades": stats.get("total_trades", 0),
                "profit": stats.get("net_profit", 0)
            })
            total_trades += stats.get("total_trades", 0)
            total_profit += stats.get("net_profit", 0)
            winning += stats.get("winning_trades", 0)
            losing += stats.get("losing_trades", 0)
            gross_profit += stats.get("gross_profit", 0)
            gross_loss += stats.get("gross_loss", 0)
        else:
            daily_breakdown.append({
                "date": day.isoformat(),
                "trades": 0,
                "profit": 0
            })

    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

    return {
        "success": True,
        "data": {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "summary": {
                "total_trades": total_trades,
                "winning_trades": winning,
                "losing_trades": losing,
                "win_rate": round(win_rate, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "net_profit": round(total_profit, 2)
            },
            "daily_breakdown": daily_breakdown
        }
    }


@router.get("/monthly")
async def monthly_report(
    year: int = Query(None),
    month: int = Query(None, ge=1, le=12),
    user: dict = Depends(get_current_user)
):
    """
    گزارش ماهانه

    شامل:
    - خلاصه ماه
    - تفکیک هفتگی
    - توزیع نمادها و سشن‌ها
    """
    today = datetime.utcnow()
    year = year or today.year
    month = month or today.month

    # محاسبه روزهای ماه
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    month_start = datetime(year, month, 1).date()
    month_end = (next_month - timedelta(days=1)).date()

    # دریافت آمار
    total_trades = 0
    total_profit = 0
    winning = 0
    losing = 0

    current = month_start
    while current <= month_end:
        stats = await db.select_one("daily_statistics", {
            "user_id": user["id"],
            "stat_date": current.isoformat()
        })
        if stats:
            total_trades += stats.get("total_trades", 0)
            total_profit += stats.get("net_profit", 0)
            winning += stats.get("winning_trades", 0)
            losing += stats.get("losing_trades", 0)
        current += timedelta(days=1)

    win_rate = (winning / total_trades * 100) if total_trades > 0 else 0

    return {
        "success": True,
        "data": {
            "month": f"{year}-{month:02d}",
            "summary": {
                "total_trades": total_trades,
                "winning_trades": winning,
                "losing_trades": losing,
                "win_rate": round(win_rate, 2),
                "net_profit": total_profit
            }
        }
    }


@router.get("/performance")
async def performance_stats(
    period: str = Query(default="month", regex="^(week|month|year|all)$"),
    user: dict = Depends(get_current_user)
):
    """
    آمار عملکرد

    شامل:
    - معیارهای عملکرد
    - نمودار equity
    - توزیع‌ها
    """
    # محاسبه بازه
    today = datetime.utcnow().date()

    if period == "week":
        start_date = today - timedelta(days=7)
    elif period == "month":
        start_date = today - timedelta(days=30)
    elif period == "year":
        start_date = today - timedelta(days=365)
    else:
        start_date = datetime(2020, 1, 1).date()

    # دریافت معاملات
    trades = await db.select_many(
        "trades",
        filters={
            "user_id": user["id"],
            "status": "closed"
        },
        order_by="closed_at",
        limit=1000
    )

    if not trades:
        return {
            "success": True,
            "data": {
                "period": period,
                "metrics": {
                    "total_trades": 0,
                    "win_rate": 0,
                    "profit_factor": 0,
                    "net_profit": 0,
                    "avg_trade": 0
                }
            }
        }

    # محاسبه معیارها
    total = len(trades)
    wins = [t for t in trades if t.get("profit_money", 0) > 0]
    losses = [t for t in trades if t.get("profit_money", 0) < 0]

    gross_profit = sum(t.get("profit_money", 0) for t in wins)
    gross_loss = abs(sum(t.get("profit_money", 0) for t in losses))
    total_profit = gross_profit - gross_loss

    win_rate = (len(wins) / total * 100) if total > 0 else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
    avg_trade = total_profit / total if total > 0 else 0

    return {
        "success": True,
        "data": {
            "period": period,
            "metrics": {
                "total_trades": total,
                "winning_trades": len(wins),
                "losing_trades": len(losses),
                "win_rate": round(win_rate, 2),
                "profit_factor": round(profit_factor, 2),
                "net_profit": round(total_profit, 2),
                "avg_trade": round(avg_trade, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2)
            }
        }
    }
