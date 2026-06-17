"""
روت‌های سیگنال‌ها

نویسنده: MT5 Trading Team
"""

from fastapi import APIRouter, Depends, Query
from typing import Optional
from datetime import datetime

from ...core.logger import get_logger
from ...core.enums import SignalStatus, SignalStrength
from ...database import db
from .auth import get_current_user

logger = get_logger("api.signals")
router = APIRouter()


@router.get("/")
async def list_signals(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0),
    user: dict = Depends(get_current_user)
):
    """
    لیست سیگنال‌ها

    فیلترهای موجود:
    - status: generated, sent, executed, expired
    - symbol: نماد
    - direction: buy, sell
    - min_score: حداقل امتیاز
    """
    filters = {"user_id": user["id"]}

    if status:
        filters["status"] = status
    if symbol:
        filters["symbol"] = symbol
    if direction:
        filters["direction"] = direction

    signals = await db.select_many(
        "signals",
        filters=filters,
        order_by="generated_at",
        order_desc=True,
        limit=limit,
        offset=offset
    )

    # فیلتر بر اساس min_score (بعد از دریافت)
    if min_score:
        signals = [s for s in signals if s.get("total_score", 0) >= min_score]

    return {
        "success": True,
        "data": {
            "signals": signals,
            "count": len(signals),
            "limit": limit,
            "offset": offset
        }
    }


@router.get("/active")
async def get_active_signals(user: dict = Depends(get_current_user)):
    """دریافت سیگنال‌های فعال"""
    now = datetime.utcnow().isoformat()

    signals = await db.select_many(
        "signals",
        filters={
            "user_id": user["id"],
            "status": "generated"
        },
        order_by="generated_at",
        order_desc=True,
        limit=10
    )

    # فیلتر سیگنال‌های منقضی نشده
    active = [
        s for s in signals
        if s.get("valid_until") and s["valid_until"] > now
    ]

    return {
        "success": True,
        "data": {
            "active_signals": active,
            "count": len(active)
        }
    }


@router.get("/{signal_id}")
async def get_signal(
    signal_id: str,
    user: dict = Depends(get_current_user)
):
    """جزئیات یک سیگنال"""
    signal = await db.select_one("signals", {
        "id": signal_id,
        "user_id": user["id"]
    })

    if not signal:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="سیگنال یافت نشد")

    return {
        "success": True,
        "data": signal
    }
