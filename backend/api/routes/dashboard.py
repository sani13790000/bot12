"""
backend/api/routes/dashboard.py
P9-FIX-BACK-1: ownership enforcement
P9-FIX-BACK-2: no error detail leaked
P9-FIX-BACK-3: equity-curve fallback
P9-FIX-BACK-4: today_profit added
P9-FIX-BACK-5: bot_status endpoint
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from backend.core.deps_v2 import get_auth_context, AuthContext
from backend.services.trade_service import TradeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_trade_svc = TradeService()


class DashboardStats(BaseModel):
    balance:        float
    equity:         float
    today_profit:   float
    total_pnl:      float
    win_rate:       float
    total_trades:   int
    open_trades:    int
    security_score: int
    drawdown_pct:   float
    bot_online:     bool


class EquityPoint(BaseModel):
    timestamp: str
    equity:    float
    balance:   float
    drawdown:  float


class EquityCurveResponse(BaseModel):
    points: list[EquityPoint]


class BotStatus(BaseModel):
    online:          bool
    last_heartbeat:  Optional[str]
    mode:            str
    kill_switch:     bool
    margin_level:    Optional[float]
    open_trades:     int


def _safe(fn):
    """Wrap coroutine to catch exceptions and return None."""
    import functools
    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except Exception:
            return None
    return wrapper


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    ctx: AuthContext = Depends(get_auth_context),
) -> DashboardStats:
    uid = ctx.user_id
    try:
        stats = await _trade_svc.get_dashboard_stats(user_id=uid)
    except Exception:
        logger.exception("get_stats failed for user %s", uid)
        raise HTTPException(status_code=503, detail="\u0633\u0631\u0648\u06cc\u0633 \u062f\u0627\u0634\u0628\u0648\u0631\u062f \u0645\u0648\u0642\u062a\u0627\u064b \u062f\u0631 \u062f\u0633\u062a\u0631\u0633 \u0646\u06cc\u0633\u062a")
    return DashboardStats(
        balance        = stats.get("balance",        0.0),
        equity         = stats.get("equity",         0.0),
        today_profit   = stats.get("today_profit",   0.0),
        total_pnl      = stats.get("total_pnl",      0.0),
        win_rate       = stats.get("win_rate",        0.0),
        total_trades   = stats.get("total_trades",   0),
        open_trades    = stats.get("open_trades",    0),
        security_score = stats.get("security_score", 0),
        drawdown_pct   = stats.get("drawdown_pct",   0.0),
        bot_online     = stats.get("bot_online",     False),
    )


@router.get("/equity-curve", response_model=EquityCurveResponse)
async def get_equity_curve(
    days: int = Query(default=30, ge=1, le=365),
    ctx: AuthContext = Depends(get_auth_context),
) -> EquityCurveResponse:
    uid = ctx.user_id
    try:
        raw = await _trade_svc.get_equity_curve(user_id=uid, days=days)
    except Exception:
        logger.exception("get_equity_curve failed for user %s", uid)
        return EquityCurveResponse(points=[])

    points: list[EquityPoint] = []
    for row in (raw or []):
        try:
            points.append(EquityPoint(
                timestamp = row["timestamp"] if isinstance(row["timestamp"], str)
                            else row["timestamp"].isoformat(),
                equity    = float(row.get("equity", 0.0)),
                balance   = float(row.get("balance", 0.0)),
                drawdown  = float(row.get("drawdown", 0.0)),
            ))
        except Exception:
            continue

    if not points:
        now = datetime.now(timezone.utc).isoformat()
        points = [EquityPoint(timestamp=now, equity=0.0, balance=0.0, drawdown=0.0)]

    return EquityCurveResponse(points=points)


@router.get("/bot-status", response_model=BotStatus)
async def get_bot_status(
    ctx: AuthContext = Depends(get_auth_context),
) -> BotStatus:
    uid = ctx.user_id
    try:
        status_data = await _trade_svc.get_bot_status(user_id=uid)
    except Exception:
        logger.exception("get_bot_status failed for user %s", uid)
        return BotStatus(
            online=False, last_heartbeat=None, mode="STOPPED",
            kill_switch=False, margin_level=None, open_trades=0
        )
    return BotStatus(
        online         = status_data.get("online",         False),
        last_heartbeat = status_data.get("last_heartbeat", None),
        mode           = status_data.get("mode",           "STOPPED"),
        kill_switch    = status_data.get("kill_switch",    False),
        margin_level   = status_data.get("margin_level",   None),
        open_trades    = status_data.get("open_trades",    0),
    )
