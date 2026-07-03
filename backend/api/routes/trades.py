"""
backend/api/routes/trades.py

Fix C-4: status Query param renamed to status_filter.
Fix C-5: Added router prefix /trades.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional

from backend.core.auth import require_auth

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/")
async def list_trades(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
    user=Depends(require_auth),
) -> list[dict[str, Any]]:
    """List trades with optional status filter."""
    return []


@router.get("/{trade_id}")
async def get_trade(
    trade_id: str,
    user=Depends(require_auth),
) -> dict[str, Any]:
    """Get a specific trade by ID."""
    raise HTTPException(status_code=404, detail="Trade not found")


@router.post("/close/{trade_id}")
async def close_trade(
    trade_id: str,
    user=Depends(require_auth),
) -> dict[str, Any]:
    """Close an open trade."""
    return {"closed": trade_id, "status": "ok"}
