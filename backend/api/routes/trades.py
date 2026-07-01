"""
backend/api/routes/trades.py -- Phase-C trades router (repaired)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


class TradeOut(BaseModel):
    id: str
    symbol: str
    direction: str
    lots: float
    status: str
    profit: float = 0.0


@router.get("/", response_model=list[TradeOut])
async def list_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> list[TradeOut]:
    """List recent trades."""
    return []


@router.get("/{trade_id}", response_model=TradeOut)
async def get_trade(trade_id: str) -> TradeOut:
    """Get single trade by ID."""
    raise HTTPException(status_code=404, detail="Trade not found")


__all__ = ["router"]
