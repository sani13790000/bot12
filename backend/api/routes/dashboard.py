"""Dashboard API routes — trading overview."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Any

from backend.core.auth import require_auth
from backend.database.connection import get_db

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_summary(user=Depends(require_auth)) -> dict[str, Any]:
    """Return high-level portfolio summary."""
    return {
        "status": "ok",
        "balance": 0.0,
        "equity": 0.0,
        "open_trades": 0,
        "daily_pnl": 0.0,
    }


@router.get("/trades")
async def get_trades(user=Depends(require_auth)) -> list[dict]:
    """Return list of recent trades."""
    return []


@router.get("/performance")
async def get_performance(user=Depends(require_auth)) -> dict[str, Any]:
    """Return performance metrics."""
    return {
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "sharpe_ratio": 0.0,
    }
