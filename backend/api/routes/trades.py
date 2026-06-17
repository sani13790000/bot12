"""
روت‌های معاملات

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from datetime import datetime

from ...core.logger import get_logger
from ...core.enums import TradeStatus, TradeDirection
from ...database import db
from .auth import get_current_user

logger = get_logger("api.trades")
router = APIRouter()


@router.get("/")
async def list_trades(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0),
    user: dict = Depends(get_current_user)
):
    """
    لیست معاملات

    فیلترهای موجود:
    - status: pending, open, closed, cancelled
    - symbol: نماد
    - direction: buy, sell
    - from_date: از تاریخ (ISO format)
    - to_date: تا تاریخ (ISO format)
    """
    filters = {"user_id": user["id"]}

    if status:
        filters["status"] = status
    if symbol:
        filters["symbol"] = symbol
    if direction:
        filters["direction"] = direction

    trades = await db.select_many(
        "trades",
        filters=filters,
        order_by="opened_at",
        order_desc=True,
        limit=limit,
        offset=offset
    )

    # فیلتر تاریخ (بعد از دریافت)
    if from_date:
        trades = [t for t in trades if t.get("opened_at") and t["opened_at"] >= from_date]
    if to_date:
        trades = [t for t in trades if t.get("opened_at") and t["opened_at"] <= to_date]

    # خلاصه
    total_profit = sum(t.get("profit_money", 0) or 0 for t in trades)

    return {
        "success": True,
        "data": {
            "trades": trades,
            "count": len(trades),
            "total_profit": total_profit,
            "limit": limit,
            "offset": offset
        }
    }


@router.get("/open")
async def get_open_positions(user: dict = Depends(get_current_user)):
    """دریافت معاملات باز"""
    trades = await db.select_many(
        "trades",
        filters={
            "user_id": user["id"],
            "status": "open"
        },
        order_by="opened_at",
        order_desc=True,
        limit=50
    )

    total_profit = sum(t.get("profit_money", 0) or 0 for t in trades)

    return {
        "success": True,
        "data": {
            "positions": trades,
            "count": len(trades),
            "total_profit": total_profit
        }
    }


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    user: dict = Depends(get_current_user)
):
    """جزئیات یک معامله"""
    trade = await db.select_one("trades", {
        "id": trade_id,
        "user_id": user["id"]
    })

    if not trade:
        raise HTTPException(status_code=404, detail="معامله یافت نشد")

    return {
        "success": True,
        "data": trade
    }


@router.post("/close/{trade_id}")
async def close_trade(
    trade_id: str,
    close_reason: str = "manual",
    user: dict = Depends(get_current_user)
):
    """بستن یک معامله"""
    trade = await db.select_one("trades", {
        "id": trade_id,
        "user_id": user["id"],
        "status": "open"
    })

    if not trade:
        raise HTTPException(status_code=404, detail="معامله باز یافت نشد")

    # به‌روزرسانی
    updated = await db.update(
        "trades",
        {"id": trade_id},
        {
            "status": "closed",
            "close_reason": close_reason,
            "closed_at": datetime.utcnow().isoformat()
        }
    )

    logger.info(f"معامله {trade_id} بسته شد")

    return {
        "success": True,
        "message": "معامله بسته شد",
        "data": updated[0] if updated else None
    }


@router.post("/close-all")
async def close_all_trades(
    direction: Optional[str] = Query(None),
    user: dict = Depends(get_current_user)
):
    """بستن همه معاملات"""
    filters = {
        "user_id": user["id"],
        "status": "open"
    }

    if direction:
        filters["direction"] = direction

    trades = await db.select_many("trades", filters=filters)

    closed_count = 0
    total_profit = 0

    for trade in trades:
        await db.update(
            "trades",
            {"id": trade["id"]},
            {
                "status": "closed",
                "close_reason": "manual",
                "closed_at": datetime.utcnow().isoformat()
            }
        )
        closed_count += 1
        total_profit += trade.get("profit_money", 0) or 0

    logger.info(f"{closed_count} معامله بسته شد")

    return {
        "success": True,
        "data": {
            "closed_count": closed_count,
            "total_profit": total_profit
        }
    }
