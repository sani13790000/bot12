"""
backend/api/routes/signals.py -- Phase-E fix

E-11: execute_signal() now calls ExecutionService.open_position() for real MT5 trade.
E-12: Added GET /{signal_id} single-signal endpoint.
E-13: lot_size added to SignalCreate schema.
E-14: Confidence gate: rejects signals below 60% confidence.
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
router = APIRouter(tags=["signals"])

_MIN_CONFIDENCE = 60.0


class SignalCreate(BaseModel):
    symbol:      str
    direction:   str
    entry_price: float
    stop_loss:   float
    take_profit: float
    confidence:  float = Field(default=0.0, ge=0.0, le=100.0)
    lot_size:    float = Field(default=0.01, gt=0, le=100)
    strategy:    Optional[str] = None
    notes:       Optional[str] = None


class SignalResponse(BaseModel):
    id:           str
    user_id:      str
    symbol:       str
    direction:    str
    entry_price:  float
    stop_loss:    float
    take_profit:  float
    confidence:   float
    lot_size:     float
    strategy:     Optional[str] = None
    notes:        Optional[str] = None
    status:       str
    mt5_ticket:   Optional[int] = None
    created_at:   str
    updated_at:   str


def _get_execution_service():
    from backend.execution.execution_service import execution_service
    return execution_service


@router.get("/", response_model=List[SignalResponse])
async def list_signals(
    signal_status: Optional[str] = Query(None, alias="status"),
    limit:         int           = Query(50, ge=1, le=200),
    offset:        int           = Query(0, ge=0),
    user:          dict          = Depends(get_current_user),
    db                           = Depends(get_db),
) -> List[SignalResponse]:
    filters: dict = {"user_id": user["sub"]}
    if signal_status:
        filters["status"] = signal_status
    rows = await db.select("signals", filters, order_by="created_at", order_desc=True, limit=limit, offset=offset)
    return [SignalResponse(**r) for r in (rows or [])]


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: str, user: dict = Depends(get_current_user), db = Depends(get_db)) -> SignalResponse:
    sig = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return SignalResponse(**sig)


@router.post("/", response_model=SignalResponse, status_code=201)
async def create_signal(body: SignalCreate, user: dict = Depends(get_current_user), db = Depends(get_db)) -> SignalResponse:
    if body.direction not in ("buy", "sell"):
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"direction must be 'buy' or 'sell'")
    now = datetime.now(timezone.utc).isoformat()
    data = {"id": str(uuid.uuid4()), "user_id": user["sub"], "symbol": body.symbol, "direction": body.direction, "entry_price": body.entry_price, "stop_loss": body.stop_loss, "take_profit": body.take_profit, "confidence": body.confidence, "lot_size": body.lot_size, "strategy": body.strategy, "notes": body.notes, "status": "pending", "mt5_ticket": None, "created_at": now, "updated_at": now}
    result = await db.insert("signals", data)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create signal")
    return SignalResponse(**result)


@router.post("/{signal_id}/execute")
async def execute_signal(signal_id: str, user: dict = Depends(get_current_user), db = Depends(get_db)) -> dict:
    sig = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    if sig.get("status") != "pending":
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"Signal is not pending")
    confidence = sig.get("confidence", 0.0)
    if confidence < _MIN_CONFIDENCE:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Signal confidence {confidence:.1f}% below minimum {_MIN_CONFIDENCE:.0f}%")
    now = datetime.now(timezone.utc).isoformat()
    try:
        svc = _get_execution_service()
        result = await svc.open_position(symbol=sig["symbol"], direction=sig["direction"], lot_size=sig.get("lot_size", 0.01), entry_price=sig["entry_price"], stop_loss=sig["stop_loss"], take_profit=sig["take_profit"], comment=f"signal:{signal_id[:8]}")
        ticket = result.get("ticket")
        await db.update("signals", {"id": signal_id}, {"status": "executed", "mt5_ticket": ticket, "executed_at": now, "updated_at": now})
        logger.info("Signal executed: id=%s ticket=%s", signal_id, ticket)
        return {"success": True, "signal_id": signal_id, "mt5_ticket": ticket}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("MT5 execution failed for signal %s: %s", signal_id, exc)
        await db.update("signals", {"id": signal_id}, {"status": "failed", "updated_at": now})
        raise HTTPException(status_code=http_status.HTTP_502_BAD_GATEWAY, detail=f"MT5 execution failed: {exc}")


@router.post("/{signal_id}/cancel")
async def cancel_signal(signal_id: str, user: dict = Depends(get_current_user), db = Depends(get_db)) -> dict:
    sig = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    if sig.get("status") not in ("pending", "active"):
        raise HTTPException(status_code=http_status.HTTP_409_CONFLICT, detail=f"Cannot cancel signal with status '{sig.get('status')}'")
    now = datetime.now(timezone.utc).isoformat()
    await db.update("signals", {"id": signal_id}, {"status": "cancelled", "updated_at": now})
    return {"success": True, "signal_id": signal_id}
