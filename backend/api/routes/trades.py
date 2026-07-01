"""
backend/api/routes/trades.py -- Phase-3 trade execution routes
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/trades', tags=['trades'])


class TradeRequest(BaseModel):
    symbol: str
    direction: str
    lots: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class TradeResponse(BaseModel):
    id: str
    symbol: str
    direction: str
    lots: float
    status: str
    entry_price: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    created_at: str


class TradeListResponse(BaseModel):
    trades: List[TradeResponse]
    total: int
    page: int
    page_size: int


@router.get('/', response_model=TradeListResponse)
async def list_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TradeListResponse:
    return TradeListResponse(trades=[], total=0, page=page, page_size=page_size)


@router.get('/{trade_id}', response_model=TradeResponse)
async def get_trade(trade_id: str) -> TradeResponse:
    raise HTTPException(status_code=404, detail='Trade not found')


@router.post('/', response_model=TradeResponse)
async def create_trade(req: TradeRequest) -> TradeResponse:
    raise HTTPException(status_code=503, detail='Trading service unavailable')


@router.delete('/{trade_id}')
async def close_trade(trade_id: str) -> Dict[str, Any]:
    return {'status': 'closed', 'id': trade_id}
