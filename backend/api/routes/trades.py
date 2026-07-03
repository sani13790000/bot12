"""
backend/api/routes/trades.py -- Phase-C fix

C-4  `status` Query param shadowed the `status` import from fastapi.
     Renamed to `trade_status`.
C-5  Missing ownership check — users can only see their own trades.
C-6  Total count was always 0 — fixed.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.core.deps import get_auth_context, AuthContext

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


class TradeOut(BaseModel):
    id:           str
    symbol:       str
    direction:    str
    volume:       float
    open_price:   float
    close_price:  Optional[float]
    profit:       Optional[float]
    open_time:    str
    close_time:   Optional[str]
    trade_status: str
    strategy:     Optional[str]


class PaginatedTrades(BaseModel):
    items: List[TradeOut]
    total: int
    page:  int
    size:  int


@router.get("/", response_model=PaginatedTrades)
async def list_trades(
    page:         int           = Query(1, ge=1),
    size:         int           = Query(20, ge=1, le=100),
    symbol:       Optional[str] = Query(None),
    trade_status: Optional[str] = Query(None),  # C-4: renamed from `status`
    ctx: AuthContext            = Depends(get_auth_context),
) -> PaginatedTrades:
    """C-5: List trades for the authenticated user only."""
    try:
        from backend.database.connection import get_db
        db     = get_db()
        offset = (page - 1) * size

        query = (
            db.table("trades")
            .select("*", count="exact")
            .eq("user_id", ctx.user_id)   # C-5: ownership enforcement
        )
        if symbol:
            query = query.eq("symbol", symbol)
        if trade_status:
            query = query.eq("status", trade_status)

        result = await query.order("open_time", desc=True).range(offset, offset + size - 1).execute()

        total = result.count or 0   # C-6: use actual count
        items = [
            TradeOut(
                id           = r["id"],
                symbol       = r["symbol"],
                direction    = r["direction"],
                volume       = r.get("volume", 0.0),
                open_price   = r.get("open_price", 0.0),
                close_price  = r.get("close_price"),
                profit       = r.get("profit"),
                open_time    = str(r.get("open_time", "")),
                close_time   = str(r["close_time"]) if r.get("close_time") else None,
                trade_status = r.get("status", "OPEN"),
                strategy     = r.get("strategy"),
            )
            for r in (result.data or [])
        ]
        return PaginatedTrades(items=items, total=total, page=page, size=size)

    except Exception as exc:
        log.error("list_trades error: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Trades service unavailable")


@router.get("/{trade_id}", response_model=TradeOut)
async def get_trade(
    trade_id: str,
    ctx: AuthContext = Depends(get_auth_context),
) -> TradeOut:
    """Get a single trade. C-5: enforce ownership."""
    try:
        from backend.database.connection import get_db
        db     = get_db()
        result = await (
            db.table("trades")
            .select("*")
            .eq("id", trade_id)
            .eq("user_id", ctx.user_id)
            .single()
            .execute()
        )
        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Trade not found")
        r = result.data
        return TradeOut(
            id=r["id"], symbol=r["symbol"], direction=r["direction"],
            volume=r.get("volume", 0.0), open_price=r.get("open_price", 0.0),
            close_price=r.get("close_price"), profit=r.get("profit"),
            open_time=str(r.get("open_time", "")),
            close_time=str(r["close_time"]) if r.get("close_time") else None,
            trade_status=r.get("status", "OPEN"),
            strategy=r.get("strategy"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("get_trade error: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Trade service unavailable")
