"""
backend/api/routes/signals.py
Galaxy Vast AI Trading Platform — Signals API Routes
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/signals', tags=['signals'])


class SignalResponse(BaseModel):
    id: str
    symbol: str
    direction: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    status: str
    created_at: str


class SignalListResponse(BaseModel):
    signals: List[SignalResponse]
    total: int
    page: int
    page_size: int


@router.get('/', response_model=SignalListResponse)
async def list_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    symbol: Optional[str] = None,
    status: Optional[str] = None,
) -> SignalListResponse:
    return SignalListResponse(signals=[], total=0, page=page, page_size=page_size)


@router.get('/{signal_id}', response_model=SignalResponse)
async def get_signal(signal_id: str) -> SignalResponse:
    raise HTTPException(status_code=404, detail='Signal not found')


@router.delete('/{signal_id}')
async def cancel_signal(signal_id: str) -> Dict[str, Any]:
    return {'status': 'cancelled', 'id': signal_id}
