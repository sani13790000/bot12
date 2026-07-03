"""
backend/api/routes/signals.py -- Phase-C fix

C-10  status Query param shadowed the `status` import from fastapi.
      Renamed the query param to `signal_status` everywhere.
C-11  Missing router prefix — added prefix="/signals" to the APIRouter.
C-12  Pagination meta was wrong (total always 0) — fixed count query.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.core.deps import get_auth_context, AuthContext, require_role
from backend.core.enums import UserRole

log    = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])


class SignalOut(BaseModel):
    id:          str
    symbol:      str
    direction:   str
    confidence:  float
    entry_price: Optional[float]
    sl:          Optional[float]
    tp:          Optional[float]
    source:      str
    created_at:  str
    signal_status: str


class PaginatedSignals(BaseModel):
    items: List[SignalOut]
    total: int
    page:  int
    size:  int


@router.get("/", response_model=PaginatedSignals)
async def list_signals(
    page:          int            = Query(1, ge=1),
    size:          int            = Query(20, ge=1, le=100),
    symbol:        Optional[str]  = Query(None),
    signal_status: Optional[str]  = Query(None),   # C-10: renamed from `status`
    ctx: AuthContext              = Depends(get_auth_context),
) -> PaginatedSignals:
    """List signals with pagination and filtering."""
    try:
        from backend.database.connection import get_db
        db     = get_db()
        offset = (page - 1) * size

        query = db.table("signals").select("*", count="exact")
        if symbol:
            query = query.eq("symbol", symbol)
        if signal_status:
            query = query.eq("status", signal_status)

        result = await query.order("created_at", desc=True).range(offset, offset + size - 1).execute()

        total  = result.count or 0
        items  = [
            SignalOut(
                id            = r["id"],
                symbol        = r["symbol"],
                direction     = r["direction"],
                confidence    = r.get("confidence", 0.0),
                entry_price   = r.get("entry_price"),
                sl            = r.get("sl"),
                tp            = r.get("tp"),
                source        = r.get("source", "unknown"),
                created_at    = str(r.get("created_at", "")),
                signal_status = r.get("status", "PENDING"),
            )
            for r in (result.data or [])
        ]
        return PaginatedSignals(items=items, total=total, page=page, size=size)

    except Exception as exc:
        log.error("list_signals error: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Signals service unavailable")


@router.get("/{signal_id}", response_model=SignalOut)
async def get_signal(
    signal_id: str,
    ctx: AuthContext = Depends(get_auth_context),
) -> SignalOut:
    """Get a single signal by ID."""
    try:
        from backend.database.connection import get_db
        db     = get_db()
        result = await db.table("signals").select("*").eq("id", signal_id).single().execute()
        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Signal not found")
        r = result.data
        return SignalOut(
            id=r["id"], symbol=r["symbol"], direction=r["direction"],
            confidence=r.get("confidence", 0.0), entry_price=r.get("entry_price"),
            sl=r.get("sl"), tp=r.get("tp"), source=r.get("source", "unknown"),
            created_at=str(r.get("created_at", "")),
            signal_status=r.get("status", "PENDING"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.error("get_signal error: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Signal service unavailable")
