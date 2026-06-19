"""
backend/api/routes/risk.py
Risk management endpoints.

Fix: removed double prefix — APIRouter prefix must NOT include /api/v1
because main.py already adds /api/v1 when including this router.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.core.deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/risk", tags=["Risk"])  # NO /api/v1 here


# ---------------------------------------------------------------------------
# Allowed symbols/timeframes (prevent injection)
# ---------------------------------------------------------------------------

_ALLOWED_SYMBOLS = frozenset({
    "XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "USDCHF",
    "AUDUSD", "USDCAD", "NZDUSD", "GBPJPY", "EURJPY",
    "EURGBP", "XAGUSD", "BTCUSD", "ETHUSD",
})


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RiskCalcRequest(BaseModel):
    symbol: str
    account_balance: float = Field(..., gt=0, le=10_000_000)
    risk_percent: float = Field(..., gt=0, le=10)       # max 10% per trade
    entry_price: float = Field(..., gt=0)
    stop_loss_price: float = Field(..., gt=0)
    take_profit_price: Optional[float] = Field(None, gt=0)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v

    @field_validator("stop_loss_price")
    @classmethod
    def _sl_not_equal_entry(cls, v: float, info) -> float:
        entry = info.data.get("entry_price")
        if entry and abs(v - entry) < 1e-10:
            raise ValueError("Stop loss cannot equal entry price")
        return v


class PositionSizeRequest(BaseModel):
    symbol: str
    account_balance: float = Field(..., gt=0)
    risk_percent: float = Field(..., gt=0, le=10)
    pip_value: float = Field(..., gt=0)
    stop_loss_pips: float = Field(..., gt=0, le=500)

    @field_validator("symbol")
    @classmethod
    def _validate_symbol(cls, v: str) -> str:
        v = v.upper().strip()
        if v not in _ALLOWED_SYMBOLS:
            raise ValueError(f"Symbol '{v}' not supported")
        return v


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/calculate")
async def calculate_risk(
    body: RiskCalcRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Calculate risk metrics for a trade."""
    risk_amount = body.account_balance * (body.risk_percent / 100)
    price_diff = abs(body.entry_price - body.stop_loss_price)

    if price_diff == 0:
        raise HTTPException(status_code=400, detail="Entry and stop loss prices cannot be equal")

    result = {
        "symbol": body.symbol,
        "account_balance": body.account_balance,
        "risk_percent": body.risk_percent,
        "risk_amount_usd": round(risk_amount, 2),
        "price_diff": round(price_diff, 5),
        "entry_price": body.entry_price,
        "stop_loss_price": body.stop_loss_price,
    }

    if body.take_profit_price:
        tp_diff = abs(body.take_profit_price - body.entry_price)
        result["take_profit_price"] = body.take_profit_price
        result["reward_amount_usd"] = round(risk_amount * (tp_diff / price_diff), 2)
        result["risk_reward_ratio"] = round(tp_diff / price_diff, 2)

    return result


@router.post("/position-size")
async def calculate_position_size(
    body: PositionSizeRequest,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Calculate optimal position size."""
    risk_amount = body.account_balance * (body.risk_percent / 100)
    lots = risk_amount / (body.stop_loss_pips * body.pip_value)

    return {
        "symbol": body.symbol,
        "recommended_lots": round(max(0.01, min(lots, 100)), 2),  # clamp 0.01–100
        "risk_amount_usd": round(risk_amount, 2),
        "stop_loss_pips": body.stop_loss_pips,
        "pip_value": body.pip_value,
    }


@router.get("/limits")
async def get_risk_limits(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Return platform risk limits."""
    return {
        "max_risk_percent_per_trade": 10.0,
        "max_lots": 100.0,
        "min_lots": 0.01,
        "max_open_positions": 20,
        "daily_loss_limit_percent": 5.0,
    }
