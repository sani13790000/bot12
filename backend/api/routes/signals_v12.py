"""backend/api/routes/signals_v12.py — Phase 12
P12-FIX-PAG-1,2: offset_pagination max 100
P12-FIX-OLA-1:   assert_owns per resource
P12-FIX-ERR-1:   standardized error codes
P12-FIX-LEAK-1:  no detail=str(exc)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from ...core.error_codes import EC, api_error
from ...core.object_auth import assert_owns
from ...core.pagination import OffsetPage, build_paged_response, offset_pagination

router = APIRouter()

_ALLOWED_SYMBOLS = frozenset({
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "USDCAD", "NZDUSD", "GBPJPY", "EURJPY",
    "EURGBP", "XAGUSD", "BTCUSD", "ETHUSD",
    "AUDJPY", "GBPAUD", "EURAUD", "CADJPY", "CHFJPY",
    "US30", "NAS100", "SPX500",
})


class CreateSignalRequest(BaseModel):
    symbol:      str
    direction:   str   = Field(..., pattern=r"^(BUY|SELL)$")
    entry_price: float = Field(..., gt=0, lt=1_000_000)
    stop_loss:   float = Field(..., gt=0, lt=1_000_000)
    take_profit: float = Field(..., gt=0, lt=1_000_000)
    confidence:  float = Field(default=0.0, ge=0.0, le=100.0)
    strategy:    str   = Field(default="manual", max_length=64)
    notes:       Optional[str] = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v


async def _get_current_user():  # pragma: no cover
    raise NotImplementedError


@router.get("/")
async def list_signals(
    symbol:    Optional[str] = None,
    status:    Optional[str] = None,
    page:      OffsetPage    = Depends(offset_pagination),
    user: dict = Depends(_get_current_user),
) -> dict:
    try:
        from ...database import db  # type: ignore
    except ImportError:
        db = None
    filters = {"user_id": user["sub"]}
    if status:
        allowed_statuses = {"pending", "active", "executed", "cancelled", "expired"}
        if status not in allowed_statuses:
            err = api_error(EC.VALIDATION_FIELD, detail=f"status must be one of {allowed_statuses}")
            raise HTTPException(status_code=422, detail=err.to_response())
        filters["status"] = status
    if symbol:
        sym = symbol.upper().strip()
        if sym not in _ALLOWED_SYMBOLS:
            err = api_error(EC.VALIDATION_SYMBOL, detail=f"Symbol '{sym}' not supported")
            raise HTTPException(status_code=422, detail=err.to_response())
        filters["symbol"] = sym
    try:
        signals = await db.select_many("signals", filters=filters, order_by="created_at", order_desc=True, limit=page.limit, offset=page.offset) if db else []
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    return build_paged_response(signals, page)


@router.get("/{signal_id}")
async def get_signal(signal_id: str, user: dict = Depends(_get_current_user)) -> dict:
    try:
        from ...database import db  # type: ignore
        sig = await db.select_one("signals", {"id": signal_id})
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    return assert_owns(sig, user)


@router.post("/", status_code=201)
async def create_signal(body: CreateSignalRequest, user: dict = Depends(_get_current_user)) -> dict:
    now  = datetime.now(timezone.utc).isoformat()
    data = {"id": str(uuid.uuid4()), "user_id": user["sub"], "symbol": body.symbol, "direction": body.direction, "entry_price": body.entry_price, "stop_loss": body.stop_loss, "take_profit": body.take_profit, "confidence": body.confidence, "strategy": body.strategy, "notes": body.notes, "status": "pending", "created_at": now, "updated_at": now}
    try:
        from ...database import db  # type: ignore
        result = await db.insert("signals", data)
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    if not result:
        raise HTTPException(status_code=500, detail=api_error(EC.INTERNAL_ERROR).to_response())
    return result


@router.post("/{signal_id}/execute")
async def execute_signal(signal_id: str, user: dict = Depends(_get_current_user)) -> dict:
    try:
        from ...database import db  # type: ignore
        sig = await db.select_one("signals", {"id": signal_id})
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    sig = assert_owns(sig, user)
    if sig.get("status") != "pending":
        raise HTTPException(status_code=409, detail=api_error(EC.CONFLICT, detail="Signal is not pending").to_response())
    now = datetime.now(timezone.utc).isoformat()
    try:
        from ...database import db  # type: ignore
        updated = await db.update("signals", {"id": signal_id}, {"status": "executed", "executed_at": now, "updated_at": now})
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    return {"success": True, "signal": updated[0] if updated else sig}


@router.post("/{signal_id}/cancel")
async def cancel_signal(signal_id: str, user: dict = Depends(_get_current_user)) -> dict:
    try:
        from ...database import db  # type: ignore
        sig = await db.select_one("signals", {"id": signal_id})
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    sig = assert_owns(sig, user)
    if sig.get("status") not in ("pending", "active"):
        raise HTTPException(status_code=409, detail=api_error(EC.CONFLICT, detail="Signal cannot be cancelled").to_response())
    now = datetime.now(timezone.utc).isoformat()
    try:
        from ...database import db  # type: ignore
        updated = await db.update("signals", {"id": signal_id}, {"status": "cancelled", "cancelled_at": now, "updated_at": now})
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.DATABASE_ERROR).to_response())
    return {"success": True, "signal": updated[0] if updated else sig}
