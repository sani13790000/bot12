"""
backend/api/routes/signals.py

FIX-6 (CRITICAL): import get_current_user from backend.core.deps
FIX-7 (MEDIUM): datetime.utcnow() -> datetime.now(timezone.utc)
FIX-8 (MEDIUM): user['id'] -> user['sub']
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.core.deps import get_current_user
from backend.core.logger import get_logger
from backend.database import db

logger = get_logger("api.signals")
router = APIRouter()


@router.get("/")
async def list_signals(
    status: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    limit:  int           = Query(default=50, ge=1, le=200),
    offset: int           = Query(default=0,  ge=0),
    user: dict            = Depends(get_current_user),
) -> dict:
    filters: dict = {"user_id": user["sub"]}
    if status:
        filters["status"] = status
    if symbol:
        filters["symbol"] = symbol.upper()
    signals = await db.select_many(
        "signals", filters=filters, order_by="created_at",
        order_desc=True, limit=limit, offset=offset,
    )
    return {"success": True, "data": {"signals": signals, "count": len(signals)}}


@router.get("/active")
async def get_active_signals(user: dict = Depends(get_current_user)) -> dict:
    signals = await db.select_many(
        "signals", filters={"user_id": user["sub"], "status": "active"},
        order_by="created_at", order_desc=True, limit=20,
    )
    return {"success": True, "data": {"signals": signals, "count": len(signals)}}


@router.get("/{signal_id}")
async def get_signal(signal_id: str, user: dict = Depends(get_current_user)) -> dict:
    signal = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    return {"success": True, "data": signal}


@router.post("/{signal_id}/execute")
async def execute_signal(signal_id: str, user: dict = Depends(get_current_user)) -> dict:
    signal = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.get("status") == "executed":
        raise HTTPException(status_code=400, detail="Signal already executed")
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.update("signals", {"id": signal_id},
                              {"status": "executed", "executed_at": now})
    logger.info("signal_executed id=%s user=%s", signal_id, user.get("sub"))
    return {"success": True, "data": updated[0] if updated else None}


@router.post("/{signal_id}/cancel")
async def cancel_signal(signal_id: str, user: dict = Depends(get_current_user)) -> dict:
    signal = await db.select_one("signals", {"id": signal_id, "user_id": user["sub"]})
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")
    if signal.get("status") in ("executed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel: status={signal['status']}")
    now = datetime.now(timezone.utc).isoformat()
    updated = await db.update("signals", {"id": signal_id},
                              {"status": "cancelled", "cancelled_at": now})
    logger.info("signal_cancelled id=%s user=%s", signal_id, user.get("sub"))
    return {"success": True, "data": updated[0] if updated else None}
