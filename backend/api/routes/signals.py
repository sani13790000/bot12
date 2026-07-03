"""
backend/api/routes/signals.py
Galaxy Vast AI — Signals API Routes
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any

router = APIRouter(prefix="/signals", tags=["signals"])

@router.get("/")
async def list_signals(
    symbol: str | None = Query(None),
    limit: int = Query(50, le=500),
) -> dict[str, Any]:
    return {"signals": [], "total": 0, "symbol": symbol}

@router.get("/{signal_id}")
async def get_signal(signal_id: str) -> dict[str, Any]:
    return {"id": signal_id, "status": "not_found"}

@router.post("/")
async def create_signal(payload: dict[str, Any]) -> dict[str, Any]:
    return {"created": True, "payload": payload}

__all__ = ["router"]
