"""
backend/api/routes/trades.py
Galaxy Vast AI — Trades API Routes
"""
from __future__ import annotations
from fastapi import APIRouter, Query
from typing import Any

router = APIRouter(prefix="/trades", tags=["trades"])

@router.get("/")
async def list_trades(
    symbol: str | None = Query(None),
    limit: int = Query(50, le=500),
) -> dict[str, Any]:
    return {"trades": [], "total": 0}

@router.get("/{trade_id}")
async def get_trade(trade_id: str) -> dict[str, Any]:
    return {"id": trade_id}

@router.post("/close/{trade_id}")
async def close_trade(trade_id: str) -> dict[str, Any]:
    return {"closed": True, "trade_id": trade_id}

__all__ = ["router"]
