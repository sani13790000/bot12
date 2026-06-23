"""backend/api/routes/trades_patch.py — Phase T

T-7:  GET /trades returns ALL users trades — user_id filter missing
T-8:  POST /trades/close/{ticket} — no ownership check
T-9:  GET /trades/{id} — no ownership check
T-10: Pagination missing
T-11: Trade status filter not pushed to DB
T-12: CLOSE not idempotent
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from backend.core.deps import CurrentUser

log = logging.getLogger(__name__)
router = APIRouter(prefix="/trades", tags=["Trades"])

_PAGE_SIZE_MAX = 200
_PAGE_SIZE_DEFAULT = 50
_CLOSEABLE_STATUSES = {"OPEN", "PARTIAL"}


def _assert_owns_trade(trade_row, user_id: str) -> None:
    if not trade_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    if str(trade_row.get("user_id")) != str(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")


@router.get("")
async def list_trades(
    current_user: CurrentUser,
    trade_status: Optional[str] = Query(None, alias="status"),
    symbol: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(_PAGE_SIZE_DEFAULT, ge=1, le=_PAGE_SIZE_MAX),
):
    from backend.database import db
    user_id = current_user.get("sub")
    filters: dict = {"user_id": user_id}
    if trade_status:
        filters["status"] = trade_status.upper()
    if symbol:
        filters["symbol"] = symbol.upper().strip()
    offset = (page - 1) * page_size
    try:
        rows = await db.select_many("trades", filters=filters, limit=page_size, offset=offset, order_by="opened_at", order_desc=True)
    except Exception as exc:
        log.error("list_trades DB error: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")
    return {"trades": rows, "page": page, "page_size": page_size, "count": len(rows)}


@router.get("/{trade_id}")
async def get_trade(trade_id: UUID, current_user: CurrentUser):
    from backend.database import db
    user_id = current_user.get("sub")
    try:
        row = await db.select_one("trades", {"id": str(trade_id)})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Database error")
    _assert_owns_trade(row, user_id)
    return row


@router.post("/close/{ticket}")
async def close_trade(ticket: int, current_user: CurrentUser):
    from backend.database import db
    user_id = current_user.get("sub")
    try:
        row = await db.select_one("trades", {"ticket": ticket, "user_id": user_id})
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Database error")
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
    current_status = row.get("status", "")
    if current_status not in _CLOSEABLE_STATUSES:
        return {"ticket": ticket, "status": current_status, "message": "Trade already closed"}
    try:
        from backend.execution.execution_service import ExecutionService
        svc = ExecutionService()
        result = await svc.close_position(ticket=ticket, user_id=user_id)
    except Exception as exc:
        log.error("close_trade error ticket=%s: %s", ticket, exc)
        raise HTTPException(status_code=500, detail="Close execution failed")
    return {"ticket": ticket, "result": result}
