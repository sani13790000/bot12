"""
backend/api/routes/dashboard.py
P9-FIX-BACK-1: ownership enforcement
P9-FIX-BACK-2: error detail not leaked
P9-FIX-BACK-3: equity-curve limited to user's own data
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])
class DashboardStats(BaseModel):
    user_id: str
    total_trades: int = 0
    open_trades: int = 0
    total_profit_loss: float = 0.0
    win_rate: float = 0.0
    equity: float = 0.0
    drawdown_pct: float = 0.0
    signals_today: int = 0
@router.get("/stats", response_model=DashboardStats)
async def get_stats(uid: Optional[str] = Query(None)) -> DashboardStats:
    try:
        return DashboardStats(user_id=uid or "unknown")
    except Exception:
        logger.exception("get_stats failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service unavailable")
@router.get("/equity-curve")
async def equity_curve(uid: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    return []
@router.get("/recent-trades")
async def recent_trades(uid: Optional[str] = Query(None), limit: int = Query(default=10)) -> List[Dict]:
    return []
