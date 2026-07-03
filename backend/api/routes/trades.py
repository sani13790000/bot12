"""
backend/api/routes/trades.py
Galaxy Vast AI — Trades API Routes
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status

router = APIRouter(prefix="/trades", tags=["trades"])


@router.get("/", response_model=List[Dict[str, Any]])
async def list_trades(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent trades."""
    return []


@router.get("/{trade_id}")
async def get_trade(trade_id: str):
    """Get a specific trade by ID."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")


@router.post("/close/{trade_id}")
async def close_trade(trade_id: str):
    """Close a trade."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
