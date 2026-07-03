"""
backend/api/routes/signals.py
Galaxy Vast AI — Trading Signals API Routes
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

router = APIRouter(prefix="/signals", tags=["signals"])


class SignalResponse(BaseModel):
    signal_id: str
    symbol: str
    direction: str
    confidence: float
    timestamp: str


@router.get("/", response_model=List[Dict[str, Any]])
async def list_signals(
    symbol: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List recent trading signals."""
    return []


@router.get("/{signal_id}")
async def get_signal(signal_id: str):
    """Get a specific signal by ID."""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Signal not found")
