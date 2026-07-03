from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from backend.core.deps_v2 import get_auth_context, AuthContext
from backend.services.trade_service import TradeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/dashboard', tags=['dashboard'])
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
    online:         bool
    last_heartbeat: Optional[str]
    mode:           str
    kill_switch:    bool
    margin_level:   Optional[float]
    open_trades:    int


@router.get('/stats', response_model=DashboardStats)
async def get_stats(ctx: AuthContext = Depends(get_auth_context)) -> DashboardStats:
    uid = ctx.user_id
    try:
        stats = await _trade_svc.get_dashboard_stats(user_id=uid)
    except Exception:
        logger.exception('get_stats failed for user %s', uid)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Service unavailable')
    today_profit = stats.get('today_profit') or stats.get('daily_pnl', 0.0)
    return DashboardStats(
        balance        = stats.get('balance',        0.0),
        equity         = stats.get('equity',         0.0),
        today_profit   = today_profit,
        total_pnl      = stats.get('total_pnl',      0.0),
        win_rate       = stats.get('win_rate',        0.0),
        total_trades   = stats.get('total_trades',   0),
        open_trades    = stats.get('open_trades',    0),
        security_score = stats.get('security_score', 0),
        drawdown_pct   = stats.get('drawdown_pct',   0.0),
        bot_online     = stats.get('bot_online',     False),
    )


@router.get('/equity-curve', response_model=EquityCurveResponse)
async def get_equity_curve(days: int = Query(30, ge=1, le=365), ctx: AuthContext = Depends(get_auth_context)) -> EquityCurveResponse:
    uid = ctx.user_id
    try:
        raw = await _trade_svc.get_equity_curve(user_id=uid, days=days)
    except Exception:
        logger.exception('get_equity_curve failed for user %s', uid)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Service unavailable')
    if not raw:
        return EquityCurveResponse(points=[])
    points: list[EquityPoint] = []
    for row in raw:
        try:
            ts = row['timestamp']
            if not isinstance(ts, str):
                ts = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            points.append(EquityPoint(timestamp=ts, equity=float(row.get('equity', 0.0)), balance=float(row.get('balance', 0.0)), drawdown=float(row.get('drawdown', 0.0))))
        except (KeyError, ValueError, TypeError):
            continue
    return EquityCurveResponse(points=points)


@router.get('/bot-status', response_model=BotStatus)
async def get_bot_status(ctx: AuthContext = Depends(get_auth_context)) -> BotStatus:
    uid = ctx.user_id
    try:
        data = await _trade_svc.get_bot_status(user_id=uid)
    except Exception:
        logger.exception('get_bot_status failed for user %s', uid)
        return BotStatus(online=False, last_heartbeat=None, mode='STOPPED', kill_switch=False, margin_level=None, open_trades=0)
    return BotStatus(
        online         = data.get('online',         False),
        last_heartbeat = data.get('last_heartbeat', None),
        mode           = data.get('mode',           'STOPPED'),
        kill_switch    = data.get('kill_switch',    False),
        margin_level   = data.get('margin_level',   None),
        open_trades    = data.get('open_trades',    0),
    )
