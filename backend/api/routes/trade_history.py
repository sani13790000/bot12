"""Trade history endpoint with pagination.

BUG-P3 FIX: GET /trade-history/history now supports limit/offset pagination.
  - Default/max page size from settings.ANALYTICS_PAGE_SIZE (default=100)
  - Returns total_count, has_more, page, total_pages for cursor navigation

BUG-AJ1 FIX: @router.get("/trades/history") → @router.get("/history")
  - was: main.py prefix="/trade-history" + router "/trades/history"
         → effective: /trade-history/trades/history → 404
  - now: main.py prefix="/trade-history" + router "/history"
         → effective: /trade-history/history ✅
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)
router = APIRouter(tags=["trades"])


@router.get("/history")
async def get_trade_history(
    limit: int = Query(default=100, ge=1, le=500, description="Records per page"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    status: Optional[str] = Query(default="closed", description="Trade status filter"),
    days: int = Query(default=90, ge=1, le=3650, description="Lookback window in days"),
) -> JSONResponse:
    """Paginated trade history. BUG-P3 + BUG-AJ1 fix."""
    from backend.core.config import get_settings

    _s = get_settings()
    limit = min(limit, _s.ANALYTICS_PAGE_SIZE)  # cap at configured max

    try:
        from backend.database.connection import get_db_client

        db = await get_db_client()
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        q = (
            db.table("trades")
            .select(
                "id,symbol,direction,entry_price,exit_price,"
                "stop_loss,take_profit,pnl,status,"
                "opened_at,closed_at,commission,notes",
                count="exact",
            )
            .gte("opened_at", since)
            .order("opened_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if symbol:
            q = q.eq("symbol", symbol.upper())
        if status:
            q = q.eq("status", status)

        r = await asyncio.wait_for(asyncio.to_thread(lambda: q.execute()), timeout=10.0)
        total = r.count or 0
        return JSONResponse(
            {
                "trades": r.data or [],
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
                "page": (offset // limit) + 1,
                "total_pages": max(1, -(-total // limit)),
            }
        )
    except Exception as exc:
        log.warning("get_trade_history error: %s", exc)
        return JSONResponse(
            {"trades": [], "total": 0, "limit": limit, "offset": offset, "has_more": False},
            status_code=500,
        )
