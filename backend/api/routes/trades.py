"""
backend/api/routes/trades.py

FIX-3 (CRITICAL): from .auth import get_current_user
  - routes/auth.py does NOT re-export get_current_user at module level
  - Fix: import directly from backend.core.deps
FIX-4 (HIGH): user['id'] -> user['sub'] - JWT payload key is 'sub'
FIX-5 (MEDIUM): datetime.utcnow() -> datetime.now(timezone.utc)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.deps import get_current_user
from backend.core.logger import get_logger
from backend.database import db

logger = get_logger("api.trades")
router = APIRouter()


@router.get("/")
async def list_trades(
    status:    Optional[str] = Query(None),
    symbol:    Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date:   Optional[str] = Query(None),
    limit:     int           = Query(default=50, ge=1, le=100),
    offset:    int           = Query(default=0,  ge=0),
    user: dict = Depends(get_current_user),
) -> dict:
    filters: dict = {"user_id": user["sub"]}
    if status:
        filters["status"] = status
    if symbol:
        filters["symbol"] = symbol.upper()
    if direction:
        filters["direction"] = direction
    trades = await db.select_many(
        "trades", filters=filters, order_by="opened_at",
        order_desc=True, limit=limit, offset=offset,
    )
    if from_date:
        trades = [t for t in trades if t.get("opened_at", "") >= from_date]
    if to_date:
        trades = [t for t in trades if t.get("opened_at", "") <= to_date]
    total_profit = sum(float(t.get("profit_money") or 0) for t in trades)
    return {"success": True, "data": {"trades": trades, "count": len(trades),
            "total_profit": round(total_profit, 2), "limit": limit, "offset": offset}}


@router.get("/open")
async def get_open_positions(user: dict = Depends(get_current_user)) -> dict:
    trades = await db.select_many(
        "trades", filters={"user_id": user["sub"], "status": "open"},
        order_by="opened_at", order_desc=True, limit=50,
    )
    total_profit = sum(float(t.get("profit_money") or 0) for t in trades)
    return {"success": True, "data": {"positions": trades, "count": len(trades),
            "total_profit": round(total_profit, 2)}}


@router.get("/{trade_id}")
async def get_trade(trade_id: str, user: dict = Depends(get_current_user)) -> dict:
    trade = await db.select_one("trades", {"id": trade_id, "user_id": user["sub"]})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return {"success": True, "data": trade}


@router.post("/close/{trade_id}")
async def close_trade(
    trade_id: str, close_reason: str = "manual",
    user: dict = Depends(get_current_user),
) -> dict:
    trade = await db.select_one("trades", {"id": trade_id, "user_id": user["sub"], "status": "open"})
    if not trade:
        raise HTTPException(status_code=404, detail="Open trade not found")
    closed_at = datetime.now(timezone.utc).isoformat()
    updated = await db.update("trades", {"id": trade_id},
                              {"status": "closed", "close_reason": close_reason, "closed_at": closed_at})
    logger.info("trade_closed trade_id=%s user=%s", trade_id, user.get("sub"))
    return {"success": True, "message": "Trade closed", "data": updated[0] if updated else None}


@router.post("/close-all")
async def close_all_trades(
    direction: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
) -> dict:
    filters: dict = {"user_id": user["sub"], "status": "open"}
    if direction:
        filters["direction"] = direction
    trades = await db.select_many("trades", filters=filters)
    closed_at = datetime.now(timezone.utc).isoformat()
    closed_count, total_profit = 0, 0.0
    for trade in trades:
        await db.update("trades", {"id": trade["id"]},
                        {"status": "closed", "close_reason": "manual", "closed_at": closed_at})
        closed_count += 1
        total_profit += float(trade.get("profit_money") or 0)
    logger.info("close_all user=%s closed=%d", user.get("sub"), closed_count)
    return {"success": True, "data": {"closed_count": closed_count,
            "total_profit": round(total_profit, 2)}}
