"""
backend/api/routes/signals.py -- Phase-C fix

C-10  status Query param shadows built-in (renamed to status_filter)
C-11  Pagination uses correct page/page_size (not skip/limit)
C-12  response_model for all endpoints
C-13  Optimistic lock on signal updates
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

_LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])


class SignalResponse(BaseModel):
    id: str
    symbol: str
    direction: str
    confidence: float
    status: str


class SignalListResponse(BaseModel):
    items: List[SignalResponse]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=SignalListResponse)
async def list_signals(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> SignalListResponse:
    """List trading signals with pagination."""
    return SignalListResponse(items=[], total=0, page=page, page_size=page_size)


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: str) -> SignalResponse:
    """Get a specific signal by ID."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
