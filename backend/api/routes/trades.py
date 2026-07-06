"""
backend/api/routes/trades.py -- Phase-E fix

E-7: open_trade() now calls ExecutionService.open_position() after DB insert.
     On MT5 failure: DB record rolled back to status='failed'.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel, Field

from backend.core.deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["trades"])


# ── models ────────────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id: str
    symbol: str
    direction: str
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float
    status: str
    pnl: Optional[float] = None
    opened_at: str
    closed_at: Optional[str] = None


class OpenTradeRequest(BaseModel):
    symbol: str = Field(..., example="EURUSD")
    direction: str = Field(..., example="BUY")
    entry_price: float
    stop_loss: float
    take_profit: float
    volume: float = Field(default=0.01, gt=0.0)


class CloseTradeRequest(BaseModel):
    exit_price: float


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_db():
    from backend.database.connection import get_db_client
    return get_db_client()


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[TradeResponse])
async def list_trades(
    status: Optional[str] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    _user=Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """List trades with optional filters."""
    try:
        db = _get_db()
        q = db.table("trades").select("*").order("opened_at", desc=True).limit(limit)
        if status:
            q = q.eq("status", status)
        if symbol:
            q = q.eq("symbol", symbol.upper())
        resp = q.execute()
        return resp.data or []
    except Exception as exc:
        log.error("trades/list error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(
    trade_id: str,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Get a single trade by ID."""
    try:
        db = _get_db()
        resp = db.table("trades").select("*").eq("id", trade_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Trade not found")
        return resp.data
    except HTTPException:
        raise
    except Exception as exc:
        log.error("trades/get error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/", response_model=TradeResponse, status_code=201)
async def open_trade(
    req: OpenTradeRequest,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Open a new trade via ExecutionService (real MT5). BUG-E7 FIX."""
    try:
        from datetime import datetime, timezone
        db = _get_db()
        payload = {
            "symbol": req.symbol.upper(),
            "direction": req.direction.upper(),
            "entry_price": req.entry_price,
            "stop_loss": req.stop_loss,
            "take_profit": req.take_profit,
            "volume": req.volume,
            "status": "pending",
            "opened_at": datetime.now(timezone.utc).isoformat(),
        }
        insert_resp = db.table("trades").insert(payload).execute()
        if not insert_resp.data:
            raise HTTPException(status_code=500, detail="DB insert failed")
        trade = insert_resp.data[0]
        trade_id = trade["id"]
        try:
            from backend.execution.execution_service import ExecutionService
            svc = ExecutionService()
            mt5_ticket = await svc.open_position(
                symbol=req.symbol.upper(),
                direction=req.direction.upper(),
                entry_price=req.entry_price,
                stop_loss=req.stop_loss,
                take_profit=req.take_profit,
                volume=req.volume,
            )
            db.table("trades").update({"status": "open", "mt5_ticket": str(mt5_ticket)}).eq("id", trade_id).execute()
            trade["status"] = "open"
        except Exception as mt5_exc:
            log.error("trades/open MT5 failed: %s", mt5_exc)
            db.table("trades").update({"status": "failed", "error": str(mt5_exc)}).eq("id", trade_id).execute()
            trade["status"] = "failed"
        return trade
    except HTTPException:
        raise
    except Exception as exc:
        log.error("trades/open error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{trade_id}/close")
async def close_trade(
    trade_id: str,
    req: CloseTradeRequest,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Close an open trade."""
    try:
        db = _get_db()
        resp = db.table("trades").select("*").eq("id", trade_id).single().execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Trade not found")
        trade = resp.data
        if trade.get("status") != "open":
            raise HTTPException(status_code=400, detail=f"Trade status is '{trade['status']}' — only open trades can be closed")
        pnl = (req.exit_price - trade["entry_price"]) * trade["volume"] * (1 if trade["direction"] == "BUY" else -1) * 100000
        from datetime import datetime, timezone
        db.table("trades").update({
            "status": "closed",
            "exit_price": req.exit_price,
            "pnl": round(pnl, 2),
            "closed_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", trade_id).execute()
        return {"ok": True, "trade_id": trade_id, "pnl": round(pnl, 2), "exit_price": req.exit_price}
    except HTTPException:
        raise
    except Exception as exc:
        log.error("trades/close error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/open/list")
async def list_open_trades(_user=Depends(get_current_user)) -> Dict[str, Any]:
    """List all currently open trades."""
    try:
        db = _get_db()
        resp = db.table("trades").select("*").eq("status", "open").order("opened_at", desc=True).execute()
        return {"ok": True, "trades": resp.data or [], "count": len(resp.data or [])}
    except Exception as exc:
        log.error("trades/open/list error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
