"""backend/api/routes/signals_patch.py — Phase T

T-1: GET /signals returns signals owned by current user only
T-2: POST /signals missing input validation
T-3: DELETE /signals/{id} missing ownership check
T-4: GET /signals/{id} missing ownership check
T-5: signal expiry not enforced on list endpoint
T-6: pagination cap missing
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from backend.core.deps import get_current_user, CurrentUser

log = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["Signals"])

_VALID_DIRECTIONS = {"BUY", "SELL"}
_VALID_SYMBOLS = {
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","NZDUSD","USDCAD",
    "EURGBP","EURJPY","GBPJPY","EURAUD","GBPAUD","AUDJPY","CADJPY",
    "XAUUSD","XAGUSD","BTCUSD","ETHUSD","LTCUSD","XRPUSD",
    "US30","NAS100","US500","GER40","UK100","JPN225","AUS200",
    "USOIL","UKOIL","NATGAS",
}
_PAGE_SIZE_MAX = 100
_PAGE_SIZE_DEFAULT = 20


class SignalCreateRequest(BaseModel):
    symbol: str = Field(..., min_length=3, max_length=10)
    direction: str = Field(...)
    score: float = Field(..., ge=0.0, le=100.0)
    entry_price: Optional[float] = Field(None, gt=0.0)
    stop_loss: Optional[float] = Field(None, gt=0.0)
    take_profit: Optional[float] = Field(None, gt=0.0)
    confidence: Optional[float] = Field(None, ge=0.0, le=100.0)
    notes: Optional[str] = Field(None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _VALID_SYMBOLS:
            raise ValueError(f"Unknown symbol '{v}'")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _VALID_DIRECTIONS:
            raise ValueError(f"direction must be BUY or SELL")
        return v


class SignalResponse(BaseModel):
    id: str
    user_id: str
    symbol: str
    direction: str
    score: float
    status: str
    created_at: str
    expires_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "SignalResponse":
        return cls(
            id=str(row.get("id", "")),
            user_id=str(row.get("user_id", "")),
            symbol=row.get("symbol", ""),
            direction=row.get("direction", ""),
            score=float(row.get("score", 0)),
            status=row.get("status", "PENDING"),
            created_at=str(row.get("created_at", "")),
            expires_at=str(row.get("expires_at", "")) if row.get("expires_at") else None,
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_owns(signal_row, user_id: str) -> None:
    """T-3/T-4: ownership — returns 404 to avoid confirming existence."""
    if not signal_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
    if str(signal_row.get("user_id")) != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")


@router.get("", summary="List signals for current user")
async def list_signals(
    current_user: CurrentUser,
    symbol: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    include_expired: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(_PAGE_SIZE_DEFAULT, ge=1, le=_PAGE_SIZE_MAX),
):
    from backend.database import db
    user_id = current_user.get("sub")
    filters: dict = {"user_id": user_id}
    if symbol:
        filters["symbol"] = symbol.upper().strip()
    if direction:
        filters["direction"] = direction.upper().strip()
    if not include_expired:
        filters["expires_gt"] = _now_iso()
    offset = (page - 1) * page_size
    try:
        rows = await db.select_many("signals", filters=filters, limit=page_size, offset=offset, order_by="created_at", order_desc=True)
    except Exception as exc:
        log.error("list_signals DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")
    return {"signals": [SignalResponse.from_row(r).model_dump() for r in rows], "page": page, "page_size": page_size, "count": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_signal(payload: SignalCreateRequest, current_user: CurrentUser):
    from backend.database import db
    import uuid as _uuid
    user_id = current_user.get("sub")
    now = _now_iso()
    signal_id = str(_uuid.uuid4())
    row = {"id": signal_id, "user_id": user_id, "symbol": payload.symbol, "direction": payload.direction, "score": payload.score, "entry_price": payload.entry_price, "stop_loss": payload.stop_loss, "take_profit": payload.take_profit, "confidence": payload.confidence, "notes": payload.notes, "status": "PENDING", "created_at": now, "updated_at": now}
    try:
        await db.insert("signals", row)
    except Exception as exc:
        log.error("create_signal DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")
    return {"id": signal_id, "status": "PENDING", "created_at": now}


@router.get("/{signal_id}")
async def get_signal(signal_id: UUID, current_user: CurrentUser):
    from backend.database import db
    user_id = current_user.get("sub")
    try:
        row = await db.select_one("signals", {"id": str(signal_id)})
    except Exception as exc:
        log.error("get_signal DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")
    _assert_owns(row, user_id)
    return SignalResponse.from_row(row).model_dump()


@router.delete("/{signal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_signal(signal_id: UUID, current_user: CurrentUser):
    from backend.database import db
    user_id = current_user.get("sub")
    try:
        row = await db.select_one("signals", {"id": str(signal_id)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Database error")
    _assert_owns(row, user_id)
    try:
        await db.delete("signals", {"id": str(signal_id)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Database error")
