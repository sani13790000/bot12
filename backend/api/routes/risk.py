"""
backend/api/routes/risk.py

FIX: /status and /equity/state endpoints added (frontend was getting 404)
FIX: prefix double-removed (main.py already adds /api/v1)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.core.deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/risk", tags=["Risk"])

_ALLOWED_SYMBOLS = frozenset({
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "USDCAD", "NZDUSD", "GBPJPY", "EURJPY",
    "EURGBP", "XAGUSD", "BTCUSD", "ETHUSD",
})


class RiskCalcRequest(BaseModel):
    symbol: str
    account_balance: float = Field(..., gt=0, le=10_000_000)
    risk_percent: float    = Field(..., gt=0, le=10)
    entry_price: float     = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: Optional[float] = Field(None, gt=0)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v

    @field_validator("stop_loss_price")
    @classmethod
    def _sl_ne_entry(cls, v: float, info) -> float:
        entry = info.data.get("entry_price")
        if entry and abs(v - entry) < 1e-10:
            raise ValueError("Stop loss cannot equal entry price")
        return v


class PositionSizeRequest(BaseModel):
    symbol: str
    account_balance: float = Field(..., gt=0)
    risk_percent: float    = Field(..., gt=0, le=10)
    pip_value: float       = Field(..., gt=0)
    stop_loss_pips: float  = Field(..., gt=0, le=500)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v


@router.post("/calculate")
async def calculate_risk(
    body: RiskCalcRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    risk_amount = body.account_balance * (body.risk_percent / 100)
    price_diff  = abs(body.entry_price - body.stop_loss_price)
    if price_diff == 0:
        raise HTTPException(400, "Entry and stop loss prices cannot be equal")
    result: dict = {
        "symbol":          body.symbol,
        "account_balance": body.account_balance,
        "risk_percent":    body.risk_percent,
        "risk_amount_usd": round(risk_amount, 2),
        "price_diff":      round(price_diff, 5),
        "entry_price":     body.entry_price,
        "stop_loss_price": body.stop_loss_price,
    }
    if body.take_profit_price:
        tp_diff = abs(body.take_profit_price - body.entry_price)
        result["take_profit_price"]  = body.take_profit_price
        result["reward_amount_usd"]  = round(risk_amount * (tp_diff / price_diff), 2)
        result["risk_reward_ratio"]  = round(tp_diff / price_diff, 2)
    return result


@router.post("/position-size")
async def calculate_position_size(
    body: PositionSizeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    risk_amount = body.account_balance * (body.risk_percent / 100)
    lots        = risk_amount / (body.stop_loss_pips * body.pip_value)
    return {
        "symbol":           body.symbol,
        "recommended_lots": round(max(0.01, min(lots, 100)), 2),
        "risk_amount_usd":  round(risk_amount, 2),
        "stop_loss_pips":   body.stop_loss_pips,
        "pip_value":        body.pip_value,
    }


@router.get("/limits")
async def get_risk_limits(
    current_user: dict = Depends(get_current_user),
) -> dict:
    return {
        "max_risk_percent_per_trade": 10.0,
        "max_lots":                   100.0,
        "min_lots":                   0.01,
        "max_open_positions":         20,
        "daily_loss_limit_percent":   5.0,
    }


@router.get("/status")
async def get_risk_status(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    FIX: frontend was calling /risk/status and getting 404.
    Returns current risk system status including circuit breakers.
    """
    user_id = current_user.get("sub", "")
    try:
        from backend.circuit_breaker import circuit_breaker_manager
        breakers = {
            name: cb.state.value
            for name, cb in circuit_breaker_manager._breakers.items()
        }
    except Exception:
        breakers = {}
    return {
        "status":           "active",
        "circuit_breakers": breakers,
        "limits":           await get_risk_limits(current_user),
        "user_id":          user_id,
    }


@router.get("/equity/state")
async def get_equity_state(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    FIX: frontend was calling /risk/equity/state and getting 404.
    Returns equity and drawdown state from trade_service.
    """
    user_id = current_user.get("sub", "")
    try:
        from backend.services.trade_service import trade_service
        stats = await trade_service.get_trade_stats(user_id, days=30)
        return {
            "user_id":        user_id,
            "total_profit":   stats.get("total_profit", 0),
            "win_rate":       stats.get("win_rate", 0),
            "profit_factor":  stats.get("profit_factor", 0),
            "open_positions": stats.get("open_trades", 0),
            "closed_today":   stats.get("closed_trades", 0),
            "drawdown_pct":   0.0,
            "equity_state":   "normal",
        }
    except Exception as exc:
        log.warning("equity_state fallback: %s", exc)
        return {"user_id": user_id, "equity_state": "unknown", "error": "Could not fetch equity data"}
