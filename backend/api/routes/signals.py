"""
backend/api/routes/signals.py
Galaxy Vast AI — Signals API Routes

Endpoints:
  GET  /signals           list user's signals (paginated)
  POST /signals           create a new signal
  POST /signals/{id}/execute  execute a pending signal
  POST /signals/{id}/cancel   cancel a pending/active signal
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field

from backend.core.auth import get_current_user
from backend.database.connection import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class SignalCreate(BaseModel):
    symbol:     str
    direction:  str           # "buy" | "sell"
    entry_price: float
    stop_loss:  float
    take_profit: float
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)
    strategy:   Optional[str] = None
    notes:      Optional[str] = None


class SignalResponse(BaseModel):
    id:          str
    user_id:     str
    symbol:      str
    direction:   str
    entry_price: float
    stop_loss:   float
    take_profit: float
    confidence:  float
    strategy:    Optional[str]
    notes:       Optional[str]
    status:      str
    created_at:  str
    updated_at:  str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/", response_model=List[SignalResponse])
async def list_signals(
    signal_status: Optional[str] = Query(None, alias="status"),
    limit:         int           = Query(50, ge=1, le=200),
    offset:        int           = Query(0, ge=0),
    user:          dict          = Depends(get_current_user),
    db                           = Depends(get_db),
) -> List[SignalResponse]:
    """List signals for the authenticated user."""
    filters: dict = {"user_id": user["sub"]}
    if signal_status:
        filters["status"] = signal_status
    rows = await db.select("signals", filters, limit=limit, offset=offset)
    return [SignalResponse(**r) for r in (rows or [])]


@router.post("/", response_model=SignalResponse, status_code=201)
async def create_signal(
    body: SignalCreate,
    user: dict = Depends(get_current_user),
    db         = Depends(get_db),
) -> dict:
    """Create a new trading signal."""
    now = datetime.now(timezone.utc).isoformat()
    data = {
        "id":          str(uuid.uuid4()),
        "user_id":     user["sub"],
        "symbol":      body.symbol,
        "direction":   body.direction,
        "entry_price": body.entry_price,
        "stop_loss":   body.stop_loss,
        "take_profit": body.take_profit,
        "confidence":  body.confidence,
        "strategy":    body.strategy,
        "notes":       body.notes,
        "status":      "pending",
        "created_at":  now,
        "updated_at":  now,
    }
    result = await db.insert("signals", data)
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create signal")
    return result


@router.post("/{signal_id}/execute")
async def execute_signal(
    signal_id: str,
    user:      dict = Depends(get_current_user),
    db               = Depends(get_db),
) -> dict:
    sig = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    if sig.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Signal not pending")
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.update(
        "signals",
        {"id": signal_id},
        {"status": "executed", "executed_at": now, "updated_at": now},
    )
    return {"success": True, "signal": updated[0] if updated else sig}


@router.post("/{signal_id}/cancel")
async def cancel_signal(
    signal_id: str,
    user:      dict = Depends(get_current_user),
    db               = Depends(get_db),
) -> dict:
    sig = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    if sig.get("status") not in ("pending", "active"):
        raise HTTPException(status_code=409, detail="Cannot cancel signal")
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.update(
        "signals",
        {"id": signal_id},
        {"status": "cancelled", "cancelled_at": now, "updated_at": now},
    )
    return {"success": True, "signal": updated[0] if updated else sig}
