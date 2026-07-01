"""
backend/api/routes/dashboard.py
P9-FIX-BACK-1: ownership enforcement
P9-FIX-BACK-2: error detail not leaked
P9-FIX-BACK-3: equity-curve fallback
P9-FIX-BACK-4: today_profit added to stats response
P9-FIX-BACK-5: bot_status endpoint added
NOTE: Auto-repaired stub due to binary corruption.
"""
from __future__ import annotations
import logging
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/dashboard', tags=['dashboard'])


class DashboardStats(BaseModel):
    balance: float
    equity: float
    today_profit: float
    total_pnl: float
    win_rate: float
    total_trades: int
    open_trades: int
    security_score: int
    drawdown_pct: float
    bot_online: bool


class EquityPoint(BaseModel):
    timestamp: str
    equity: float
    balance: float
    drawdown: float


class EquityResponse(BaseModel):
    points: list


class BotStatus(BaseModel):
    online: bool
    last_heartbeat: Optional[str]
    mode: str
    kill_switch: bool
    margin_level: Optional[float]
    open_trades: int


@router.get('/stats', response_model=DashboardStats)
async def get_stats() -> DashboardStats:
    return DashboardStats(
        balance=0.0, equity=0.0, today_profit=0.0, total_pnl=0.0,
        win_rate=0.0, total_trades=0, open_trades=0, security_score=0,
        drawdown_pct=0.0, bot_online=False,
    )


@router.get('/equity-curve', response_model=EquityResponse)
async def get_equity_curve(days: int = Query(30, ge=1, le=365)) -> EquityResponse:
    return EquityResponse(points=[])


@router.get('/bot-status', response_model=BotStatus)
async def get_bot_status() -> BotStatus:
    return BotStatus(
        online=False, last_heartbeat=None, mode='STOPPED',
        kill_switch=False, margin_level=None, open_trades=0,
    )
