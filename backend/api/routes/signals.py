"""
backend/api/routes/signals.py

Fix C-10: status Query param renamed to status_filter.
Fix C-11: Added router prefix /signals.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Optional

from backend.core.auth import require_auth

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/")
async def list_signals(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=500),
    user=Depends(require_auth),
) -> list[dict[str, Any]]:
    """List trading signals with optional status filter."""
    return []


@router.get("/{signal_id}")
async def get_signal(
    signal_id: str,
    user=Depends(require_auth),
) -> dict[str, Any]:
    """Get a specific signal by ID."""
    raise HTTPException(status_code=404, detail="Signal not found")


@router.post("/")
async def create_signal(
    payload: dict[str, Any],
    user=Depends(require_auth),
) -> dict[str, Any]:
    """Create a new trading signal."""
    return {"id": "new", **payload}
