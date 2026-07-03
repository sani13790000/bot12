"""
backend/api/routes/trades.py -- Phase-C fix

C-4  `status` Query param shadowed the `status` FastAPI module import.
     Renamed param to `trade_status` and aliased with Query(alias="status").
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user
from backend.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class TradeCreate(BaseModel):
    symbol:      str
    direction:   str            # "buy" | "sell"
    lot_size:    float = Field(gt=0, le=100)
    entry_price: float
    stop_loss:   float
    take_profit: float
    strategy:    Optional[str] = None
    comment:     Optional[str] = None


class TradeResponse(BaseModel):
    id:          str
    user_id:     str
    symbol:      str
    direction:   str
    lot_size:    float
    entry_price: float
    stop_loss:   float
    take_profit: float
    status:      str
    strategy:    Optional[str]
    comment:     Optional[str]
    opened_at:   str
    closed_at:   Optional[str]
    pnl:         Optional[float]


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/", response_model=List[TradeResponse])
async def list_trades(
    trade_status: Optional[str] = Query(None, alias="status"),
    limit:        int           = Query(50, ge=1, le=500),
    offset:       int           = Query(0, ge=0),
    user:         dict          = Depends(get_current_user),
    db                          = Depends(get_db),
) -> List[TradeResponse]:
    """List trades for the authenticated user."""
    filters: dict = {"user_id": user["sub"]}
    if trade_status:
        filters["status"] = trade_status
    rows = await db.select("trades", filters, limit=limit, offset=offset)
    return [TradeResponse(**r) for r in (rows or [])]


@router.post("/", response_model=TradeResponse, status_code=201)
async def open_trade(
    body: TradeCreate,
    user: dict = Depends(get_current_user),
    db         = Depends(get_db),
) -> dict:
    """Open a new trade."""
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id":          str(uuid.uuid4()),
        "user_id":     user["sub"],
        "symbol":      body.symbol,
        "direction":   body.direction,
        "lot_size":    body.lot_size,
        "entry_price": body.entry_price,
        "stop_loss":   body.stop_loss,
        "take_profit": body.take_profit,
        "status":      "open",
        "strategy":    body.strategy,
        "comment":     body.comment,
        "opened_at":   now,
        "closed_at":   None,
        "pnl":         None,
    }
    result = await db.insert("trades", data)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to open trade")
    return result


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    user:     dict = Depends(get_current_user),
    db              = Depends(get_db),
) -> dict:
    """Close an open trade."""
    trade = await db.select_one("trades", {"id": trade_id, "user_id": user["sub"]})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") != "open":
        raise HTTPException(status_code=409, detail="Trade is not open")
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.update(
        "trades",
        {"id": trade_id},
        {"status": "closed", "closed_at": now},
    )
    return {"success": True, "trade": updated[0] if updated else trade}
