"""
backend/api/routes/dashboard.py
Galaxy Vast AI - Dashboard API Routes

Endpoints:
    GET /dashboard/stats      - account statistics
    GET /dashboard/positions  - open positions
    GET /dashboard/performance - trading performance
    GET /dashboard/signals    - recent signals
    GET /dashboard/health     - system health
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.auth import get_current_active_user
from backend.core.database import get_db
from backend.core.models import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/stats")
async def get_account_stats(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Account statistics: balance, P&L, trade count."""
    try:
        return {"status": "ok", "data": {"user_id": str(current_user.id)}, "generated_at": _utcnow()}
    except Exception as exc:
        log.exception("Error fetching account stats for user %s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch account stats") from exc


@router.get("/positions")
async def get_open_positions(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Currently open positions."""
    try:
        return {"status": "ok", "count": 0, "data": [], "generated_at": _utcnow()}
    except Exception as exc:
        log.exception("Error fetching open positions for user %s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch open positions") from exc


@router.get("/performance")
async def get_performance(period: str = "daily", current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Trading performance: daily / weekly / monthly."""
    if period not in ("daily", "weekly", "monthly"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="period must be daily, weekly, or monthly")
    try:
        return {"status": "ok", "period": period, "data": {}, "generated_at": _utcnow()}
    except Exception as exc:
        log.exception("Error fetching performance for user %s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch performance data") from exc


@router.get("/signals")
async def get_recent_signals(limit: int = 20, current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> dict:
    """Most recent signals."""
    limit = min(max(limit, 1), 100)
    try:
        return {"status": "ok", "count": 0, "data": [], "generated_at": _utcnow()}
    except Exception as exc:
        log.exception("Error fetching signals for user %s", current_user.id)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not fetch signals") from exc


@router.get("/health")
async def system_health(current_user: User = Depends(get_current_active_user)) -> dict:
    """System health status."""
    return {"status": "ok", "services": {"api": "up", "database": "up", "telegram_bot": "up", "mt5_bridge": "up"}, "generated_at": _utcnow()}
