"""
backend/api/routes/signals.py
Galaxy Vast AI — Signals API Routes
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])


class SignalResponse(BaseModel):
    signal_id: str
    symbol: str
    direction: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    lot_size: float
    created_at: str
    status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SignalListResponse(BaseModel):
    signals: List[SignalResponse]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=SignalListResponse)
async def list_signals(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    symbol: Optional[str] = Query(default=None),
    status_filter: Optional[str] = Query(default=None, alias="status"),
) -> SignalListResponse:
    """List trading signals with pagination."""
    try:
        return SignalListResponse(signals=[], total=0, page=page, page_size=page_size)
    except Exception:
        logger.exception("list_signals failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable")


@router.get("/{signal_id}", response_model=SignalResponse)
async def get_signal(signal_id: str) -> SignalResponse:
    """Get a specific signal by ID."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")


@router.post("/{signal_id}/approve", status_code=status.HTTP_200_OK)
async def approve_signal(signal_id: str) -> Dict[str, str]:
    """Approve a pending signal (semi-auto mode)."""
    return {"status": "approved", "signal_id": signal_id}


@router.post("/{signal_id}/reject", status_code=status.HTTP_200_OK)
async def reject_signal(signal_id: str) -> Dict[str, str]:
    """Reject a pending signal (semi-auto mode)."""
    return {"status": "rejected", "signal_id": signal_id}


@router.get("/stats/summary")
async def signals_summary() -> Dict[str, Any]:
    """Get signal statistics summary."""
    return {
        "total_signals": 0,
        "approved": 0,
        "rejected": 0,
        "pending": 0,
        "win_rate": 0.0,
    }
