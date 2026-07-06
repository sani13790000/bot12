"""
backend/api/routes/signals.py -- Phase-E fix

E-11: execute_signal() now calls ExecutionService.open_position() for real MT5 trade.
E-12: Added GET /{signal_id} single-signal endpoint.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field

from backend.core.deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["signals"])


# ── models ────────────────────────────────────────────────────────────────────

class SignalResponse(BaseModel):
    id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float
    status: str
    created_at: str


class CreateSignalRequest(BaseModel):
    symbol: str = Field(..., example="EURUSD")
    direction: str = Field(..., example="BUY")
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float = Field(default=0.0, ge=0.0, le=100.0)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_db():
    from backend.database.connection import get_db_client
    return get_db_client()


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[SignalResponse])
async def list_signals(
    symbol: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _user=Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List trading signals with optional filters."""
    try:
        db = _get_db()
        q = db.table("signals").select("*").order("created_at", desc=True).limit(limit)
        if symbol:
            q = q.eq("symbol", symbol.upper())
        if status:
            q = q.eq("status", status)
        resp = q.execute()
        return resp.data or []
    except Exception as exc:
        log.error("signals/list error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(
    signal_id: str,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a single signal by ID."""
    try:
        db = _get_db()
        resp = db.table("signals").select("*").eq("id", signal_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Signal not found")
        return resp.data
    except HTTPException:
        raise
    except Exception as exc:
        log.error("signals/get error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/", response_model=SignalResponse, status_code=201)
async def create_signal(
    req: CreateSignalRequest,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Create a new trading signal."""
    try:
        db = _get_db()
        from datetime import datetime, timezone
        payload = {
            "symbol": req.symbol.upper(),
            "direction": req.direction.upper(),
            "entry_price": req.entry_price,
            "stop_loss": req.stop_loss,
            "take_profit": req.take_profit,
            "confidence": req.confidence,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = db.table("signals").insert(payload).execute()
        if not resp.data:
            raise HTTPException(status_code=500, detail="Insert failed")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as exc:
        log.error("signals/create error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{signal_id}/execute")
async def execute_signal(
    signal_id: str,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Execute a signal via ExecutionService (real MT5 trade). BUG-E11 FIX."""
    try:
        db = _get_db()
        resp = db.table("signals").select("*").eq("id", signal_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Signal not found")
        signal = resp.data
        if signal.get("status") != "pending":
            raise HTTPException(status_code=400, detail=f"Signal status is '{signal['status']}' — only pending signals can be executed")
        try:
            from backend.execution.execution_service import ExecutionService
            svc = ExecutionService()
            trade_id = await svc.open_position(
                symbol=signal["symbol"],
                direction=signal["direction"],
                entry_price=signal["entry_price"],
                stop_loss=signal["stop_loss"],
                take_profit=signal["take_profit"],
                volume=0.01,
                signal_id=signal_id,
            )
            db.table("signals").update({"status": "executed", "trade_id": str(trade_id)}).eq("id", signal_id).execute()
            return {"ok": True, "signal_id": signal_id, "trade_id": str(trade_id), "status": "executed"}
        except Exception as exc:
            db.table("signals").update({"status": "failed", "error": str(exc)}).eq("id", signal_id).execute()
            raise HTTPException(status_code=500, detail=f"Execution failed: {exc}")
    except HTTPException:
        raise
    except Exception as exc:
        log.error("signals/execute error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/{signal_id}", status_code=204)
async def cancel_signal(
    signal_id: str,
    _user=Depends(get_current_user),
) -> None:
    """Cancel a pending signal."""
    try:
        db = _get_db()
        resp = db.table("signals").select("status").eq("id", signal_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Signal not found")
        if resp.data.get("status") != "pending":
            raise HTTPException(status_code=400, detail="Only pending signals can be cancelled")
        db.table("signals").update({"status": "cancelled"}).eq("id", signal_id).execute()
    except HTTPException:
        raise
    except Exception as exc:
        log.error("signals/cancel error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
