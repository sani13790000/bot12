"""
backend/api/routes/trades.py -- Phase-E fix

E-7: open_trade() now calls ExecutionService.open_position() after DB insert.
E-8: close_trade() now calls ExecutionService.close_position(ticket).
E-9: Added GET /{trade_id} single-trade endpoint.
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
router = APIRouter(tags=["trades"])


class TradeCreate(BaseModel):
    symbol:      str
    direction:   str
    lot_size:    float = Field(gt=0, le=100)
    entry_price: float
    stop_loss:   float
    take_profit: float
    strategy:    Optional[str] = None
    comment:     Optional[str] = None


class TradeResponse(BaseModel):
    id:           str
    user_id:      str
    symbol:       str
    direction:    str
    lot_size:     float
    entry_price:  float
    stop_loss:    float
    take_profit:  float
    status:       str
    strategy:     Optional[str] = None
    comment:      Optional[str] = None
    opened_at:    str
    closed_at:    Optional[str] = None
    pnl:          Optional[float] = None
    mt5_ticket:   Optional[int] = None


def _get_execution_service():
    from backend.execution.execution_service import execution_service
    return execution_service


@router.get("/", response_model=List[TradeResponse])
async def list_trades(trade_status: Optional[str] = Query(None, alias="status"), limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), user: dict = Depends(get_current_user), db = Depends(get_db)) -> List[TradeResponse]:
    filters: dict = {"user_id": user["sub"]}
    if trade_status:
        filters["status"] = trade_status
    rows = await db.select("trades", filters, order_by="opened_at", order_desc=True, limit=limit, offset=offset)
    return [TradeResponse(**r) for r in (rows or [])]


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str, user: dict = Depends(get_current_user), db = Depends(get_db)) -> TradeResponse:
    trade = await db.select_one("trades", {"id": trade_id, "user_id": user["sub"]})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return TradeResponse(**trade)


@router.post("/", response_model=TradeResponse, status_code=201)
async def open_trade(body: TradeCreate, user: dict = Depends(get_current_user), db = Depends(get_db)) -> TradeResponse:
    if body.direction not in ("buy", "sell"):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"direction must be 'buy' or 'sell'")
    now = datetime.now(timezone.utc).isoformat()
    trade_id = str(uuid.uuid4())
    db_data = {"id": trade_id, "user_id": user["sub"], "symbol": body.symbol, "direction": body.direction, "lot_size": body.lot_size, "entry_price": body.entry_price, "stop_loss": body.stop_loss, "take_profit": body.take_profit, "status": "pending", "strategy": body.strategy, "comment": body.comment, "opened_at": now, "closed_at": None, "pnl": None, "mt5_ticket": None}
    record = await db.insert("trades", db_data)
    if not record:
        raise HTTPException(status_code=500, detail="Failed to create trade record")
    try:
        svc = _get_execution_service()
        result = await svc.open_position(symbol=body.symbol, direction=body.direction, lot_size=body.lot_size, entry_price=body.entry_price, stop_loss=body.stop_loss, take_profit=body.take_profit, comment=body.comment or "")
        ticket = result.get("ticket")
        actual_price = result.get("price", body.entry_price)
        updated = await db.update("trades", {"id": trade_id}, {"status": "open", "mt5_ticket": ticket, "entry_price": actual_price})
        final = updated[0] if updated else {**db_data, "status": "open", "mt5_ticket": ticket}
        logger.info("Trade opened: id=%s ticket=%s", trade_id, ticket)
        return TradeResponse(**final)
    except Exception as exc:
        logger.error("MT5 open_position failed: %s", exc)
        await db.update("trades", {"id": trade_id}, {"status": "failed"})
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=f"MT5 execution failed: {exc}")


@router.post("/{trade_id}/close")
async def close_trade(trade_id: str, user: dict = Depends(get_current_user), db = Depends(get_db)) -> dict:
    trade = await db.select_one("trades", {"id": trade_id, "user_id": user["sub"]})
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.get("status") != "open":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"Trade is not open")
    ticket = trade.get("mt5_ticket")
    if not ticket:
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail="Trade has no MT5 ticket")
    try:
        svc = _get_execution_service()
        result = await svc.close_position(ticket=ticket, symbol=trade["symbol"])
        pnl = result.get("pnl", 0.0)
    except Exception as exc:
        logger.error("MT5 close_position failed: %s", exc)
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=f"MT5 close failed: {exc}")
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.update("trades", {"id": trade_id}, {"status": "closed", "closed_at": now, "pnl": pnl})
    logger.info("Trade closed: id=%s ticket=%s pnl=%.2f", trade_id, ticket, pnl)
    return {"success": True, "trade_id": trade_id, "ticket": ticket, "pnl": pnl, "trade": updated[0] if updated else trade}
