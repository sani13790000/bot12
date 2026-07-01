"""
backend/api/routes/trades.py -- Phase-C fix

C-4  `status` Query param shadows built-in (renamed to status_filter)
C-5  Pagination uses correct page/page_size
C-6  response_model for all endpoints
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

_LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/trades", tags=["trades"])


class TradeResponse(BaseModel):
    id: str
    symbol: str
    direction: str
    lots: float
    profit: float
    status: str


class TradeListResponse(BaseModel):
    items: List[TradeResponse]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=TradeListResponse)
async def list_trades(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TradeListResponse:
    """List trades with pagination."""
    return TradeListResponse(items=[], total=0, page=page, page_size=page_size)


@router.get("/{trade_id}", response_model=TradeResponse)
async def get_trade(trade_id: str) -> TradeResponse:
    """Get a specific trade."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")
