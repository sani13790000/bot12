"""
روت‌های داشبورد

Endpointهای خلاصه برای داشبورد.

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, Query
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from ...core.logger import get_logger
from ...database import db
from ...services.trade_service import trade_service
from ...services.signal_service import signal_service
from ...services.license_service import license_service
from .auth import get_current_user

logger = get_logger("api.dashboard")
router = APIRouter()


# =====================================================
# Endpoints
# =====================================================

@router.get("/summary")
async def get_dashboard_summary(
    user: dict = Depends(get_current_user)
):
    """
    خلاصه داشبورد

    اطلاعات کلی برای داشبورد اصلی شامل:
    - آمار معاملات امروز
    - معاملات باز
    - سیگنال‌های فعال
    - آمار کلی
    """
    user_id = user.get("id")
    today = datetime.utcnow().date().isoformat()

    # معاملات امروز
    today_trades = await db.select_many(
        "trades",
        filters={"user_id": user_id},
        limit=100
    )
    today_trades = [
        t for t in today_trades
        if t.get("opened_at", "").startswith(today)
    ]

    # معاملات باز
    open_positions = await trade_service.get_open_positions(user_id)

    # سیگنال‌های فعال
    active_signals = await signal_service.get_active_signals(user_id)

    # آماد معاملات ماه
    monthly_stats = await trade_service.get_trade_stats(user_id, days=30)

    # لایسنس
    license_data = await license_service.get_user_license(user_id)

    # محاسبه سود امروز
    today_profit = sum(t.get("profit_money", 0) or 0 for t in today_trades)
    today_open = len([t for t in today_trades if t.get("status") == "open"])
    today_closed = len([t for t in today_trades if t.get("status") == "closed"])

    return {
        "success": True,
        "data": {
            "today": {
                "date": today,
                "trades": len(today_trades),
                "open": today_open,
                "closed": today_closed,
                "profit": today_profit
            },
            "open_positions": {
                "count": open_positions.get("count", 0),
                "total_profit": open_positions.get("total_profit", 0),
                "positions": open_positions.get("positions", [])[:5]
            },
            "active_signals": {
                "count": active_signals.get("count", 0),
                "signals": active_signals.get("active_signals", [])[:5]
            },
            "monthly_stats": monthly_stats,
            "license": {
                "type": license_data.get("license_type") if license_data else None,
                "status": license_data.get("status") if license_data else None,
                "expires_at": license_data.get("expires_at") if license_data else None
            }
        }
    }


@router.get("/performance")
async def get_performance(
    period: str = Query(default="month", description="دوره: day, week, month, year"),
    user: dict = Depends(get_current_user)
):
    """
    عملکرد معاملاتی

    آمار عملکرد در بازه زمانی مشخص.
    """
    period_days = {
        "day": 1,
        "week": 7,
        "month": 30,
        "year": 365
    }

    days = period_days.get(period, 30)

    stats = await trade_service.get_trade_stats(
        user_id=user.get("id"),
        days=days
    )

    daily = await trade_service.get_daily_breakdown(
        user_id=user.get("id"),
        days=min(days, 30)
    )

    return {
        "success": True,
        "data": {
            "period": period,
            "stats": stats,
            "daily_breakdown": daily
        }
    }


@router.get("/quick-stats")
async def get_quick_stats(
    user: dict = Depends(get_current_user)
):
    """
    آمار سریع

    برای نمایش در بالای داشبورد.
    """
    user_id = user.get("id")

    # تعداد معاملات باز
    open_trades = await db.count("trades", {
        "user_id": user_id,
        "status": "open"
    })

    # تعداد سیگنال‌های فعال
    signals = await signal_service.get_active_signals(user_id)

    # سود امروز
    today = datetime.utcnow().date().isoformat()
    today_trades = await db.select_many(
        "trades",
        filters={"user_id": user_id},
        limit=100
    )
    today_profit = sum(
        t.get("profit_money", 0) or 0
        for t in today_trades
        if t.get("opened_at", "").startswith(today)
    )

    # وین ریت ماه
    monthly_stats = await trade_service.get_trade_stats(user_id, days=30)

    return {
        "success": True,
        "data": {
            "open_trades": open_trades,
            "active_signals": signals.get("count", 0),
            "today_profit": today_profit,
            "win_rate": monthly_stats.get("win_rate", 0),
            "profit_factor": monthly_stats.get("profit_factor", 0)
        }
    }


@router.get("/balance")
async def get_balance_info(
    user: dict = Depends(get_current_user)
):
    """
    اطلاعات موجودی

    برای نمایش نمودار موجودی.
    """
    user_id = user.get("id")

    # معاملات بسته شده 30 روز اخیر
    trades = await db.select_many(
        "trades",
        filters={
            "user_id": user_id,
            "status": "closed"
        },
        order_by="closed_at",
        order_desc=False,
        limit=500
    )

    # محاسبه equity curve
    balance = 10000  # موجودی اولیه فرضی
    equity_curve = [{"date": "start", "balance": balance}]

    for trade in trades[:200]:
        balance += trade.get("profit_money", 0) or 0
        equity_curve.append({
            "date": trade.get("closed_at", "")[:10],
            "balance": round(balance, 2)
        })

    # محاسبه max drawdown
    peak = balance
    max_dd = 0
    for point in equity_curve:
        if point["balance"] > peak:
            peak = point["balance"]
        dd = (peak - point["balance"]) / peak * 100 if peak > 0 else 0
        max_dd = max(max_dd, dd)

    return {
        "success": True,
        "data": {
            "current_balance": balance,
            "equity_curve": equity_curve,
            "max_drawdown": round(max_dd, 2),
            "profit": balance - 10000
        }
    }


@router.get("/activity")
async def get_recent_activity(
    limit: int = Query(default=20, le=50),
    user: dict = Depends(get_current_user)
):
    """
    فعالیت‌های اخیر

    آخرین فعالیت‌های کاربر.
    """
    user_id = user.get("id")

    # لاگ‌های فعالیت
    logs = await db.select_many(
        "activity_logs",
        filters={"user_id": user_id},
        order_by="created_at",
        order_desc=True,
        limit=limit
    )

    # آخرین معاملات
    trades = await db.select_many(
        "trades",
        filters={"user_id": user_id},
        order_by="opened_at",
        order_desc=True,
        limit=5
    )

    # آخرین سیگنال‌ها
    signals = await db.select_many(
        "signals",
        filters={"user_id": user_id},
        order_by="generated_at",
        order_desc=True,
        limit=5
    )

    return {
        "success": True,
        "data": {
            "logs": logs,
            "recent_trades": trades,
            "recent_signals": signals
        }
    }
