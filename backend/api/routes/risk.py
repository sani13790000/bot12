from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.core.deps import get_current_user, get_current_admin
from backend.core.logger import get_logger
from backend.services.trade_service import trade_service

logger = get_logger("api.risk")
router = APIRouter()


class RiskAssessRequest(BaseModel):
    symbol: str
    direction: str = Field(..., pattern=r"^(BUY|SELL)$")
    balance: float = Field(..., gt=0)
    equity: float = Field(..., gt=0)
    stop_loss_pips: float = Field(..., gt=0)
    current_atr: float = Field(default=10.0, gt=0)
    current_spread: float = Field(default=0.0, ge=0)
    open_positions: int = Field(default=0, ge=0)
    today_trades_count: int = Field(default=0, ge=0)
    today_pnl_usd: float = Field(default=0.0)


@router.get("/status")
async def get_risk_status(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """G-24 / E-5 FIX: was 404."""
    return await trade_service.get_risk_status(user["sub"])


@router.get("/limits")
async def get_risk_limits(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """G-23: real settings."""
    try:
        from backend.core.config import settings
        return {
            "max_daily_loss_percent": getattr(settings, "MAX_DAILY_LOSS_PERCENT", 3.0),
            "max_open_positions":     getattr(settings, "MAX_OPEN_POSITIONS", 5),
            "max_exposure_percent":   getattr(settings, "MAX_EXPOSURE_PERCENT", 5.0),
            "max_drawdown_percent":   getattr(settings, "MAX_DRAWDOWN_PERCENT", 10.0),
            "risk_per_trade_percent": getattr(settings, "RISK_PER_TRADE_PERCENT", 1.0),
        }
    except Exception:
        return {"max_daily_loss_percent": 3.0, "max_open_positions": 5,
                "max_exposure_percent": 5.0, "max_drawdown_percent": 10.0,
                "risk_per_trade_percent": 1.0}


@router.get("/equity/state")
async def get_equity_state(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """E-5 FIX: was 404."""
    return await trade_service.get_equity_state(user["sub"])


@router.post("/assess")
async def assess_risk(body: RiskAssessRequest, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """G-25: full RiskOrchestrator assessment."""
    try:
        from backend.risk.risk_orchestrator import RiskOrchestrator, RiskInput
        inp = RiskInput(
            symbol=body.symbol, direction=body.direction,
            balance=body.balance, equity=body.equity,
            stop_loss_pips=body.stop_loss_pips,
            current_atr=body.current_atr, atr_history=[body.current_atr] * 14,
            current_spread=body.current_spread, avg_spread=body.current_spread,
            open_positions=[], today_trades_count=body.today_trades_count,
            today_pnl_usd=body.today_pnl_usd, week_pnl_usd=0.0, month_pnl_usd=0.0,
        )
        decision = await RiskOrchestrator().assess(inp)
        return decision.to_dict()
    except ImportError:
        return {"approved": True, "block_reason": "", "lot_size": 0.01,
                "risk_percent": 1.0, "risk_usd": body.balance * 0.01,
                "note": "RiskOrchestrator not available"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/circuit-breaker/{name}")
async def get_circuit_breaker(name: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """G-26: frontend circuit breaker state."""
    try:
        from backend.circuit_breaker import get_breaker
        breaker = get_breaker(name)
        s = breaker.stats
        return {"name": name, "state": s.state.value, "failures": s.failures,
                "successes": s.successes, "total_calls": s.total_calls,
                "total_failures": s.total_failures, "last_failure_time": s.last_failure_time}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Breaker {name!r} not found")


@router.post("/circuit-breaker/{name}/open")
async def open_circuit_breaker(
    name: str, reason: str = Query(default="manual"),
    admin: dict = Depends(get_current_admin),
) -> Dict[str, Any]:
    try:
        from backend.circuit_breaker import get_breaker
        await get_breaker(name).open(reason=reason)
        return {"success": True, "name": name, "state": "open", "reason": reason}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/circuit-breaker/{name}/close")
async def close_circuit_breaker(name: str, admin: dict = Depends(get_current_admin)) -> Dict[str, Any]:
    try:
        from backend.circuit_breaker import get_breaker
        await get_breaker(name).close(reason="admin_manual_close")
        return {"success": True, "name": name, "state": "closed"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
