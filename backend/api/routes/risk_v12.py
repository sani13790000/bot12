"""backend/api/routes/risk_v12.py — Phase 12 hardened.

P12-FIX-RISK-1: /halt and /resume require admin auth
P12-FIX-RISK-2: error leakage removed — standardized error codes
P12-FIX-RISK-3: naive datetime replaced with timezone.utc
P12-FIX-RISK-4: assess_risk internal errors hidden from client
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ...core.error_codes import EC, api_error
import logging

router = APIRouter()
log    = logging.getLogger("api.risk_v12")


class RiskAssessRequest(BaseModel):
    signal_id:      str   = Field(..., min_length=1, max_length=64)
    symbol:         str   = Field(..., min_length=3, max_length=12)
    direction:      str   = Field(..., pattern="^(BUY|SELL)$")
    balance:        float = Field(..., gt=0, lt=100_000_000)
    equity:         float = Field(..., gt=0, lt=100_000_000)
    stop_loss_pips: float = Field(default=20.0, gt=0, lt=10_000)
    risk_percent:   float = Field(default=1.0, gt=0, le=5)
    open_positions: list  = Field(default_factory=list, max_length=100)
    metadata:       Dict[str, Any] = Field(default_factory=dict)


class HaltRequest(BaseModel):
    reason: str = Field(default="manual_halt", min_length=1, max_length=256)


async def _get_current_user():  # pragma: no cover
    raise NotImplementedError

async def _require_admin():  # pragma: no cover
    raise NotImplementedError

async def _get_orchestrator():  # pragma: no cover
    raise NotImplementedError


@router.post("/assess")
async def assess_risk(
    body:         RiskAssessRequest,
    user:         dict = Depends(_get_current_user),
    orchestrator: Any  = Depends(_get_orchestrator),
) -> dict:
    try:
        from ...risk.risk_orchestrator import RiskInput  # type: ignore
        inp      = RiskInput(signal_id=body.signal_id, symbol=body.symbol, direction=body.direction, balance=body.balance, equity=body.equity, stop_loss_pips=body.stop_loss_pips, risk_percent=body.risk_percent, open_positions=body.open_positions, metadata=body.metadata)
        decision = await orchestrator.assess(inp)
        return decision.to_dict()
    except Exception:
        raise HTTPException(status_code=500, detail=api_error(EC.INTERNAL_ERROR).to_response())


@router.get("/status")
async def risk_status() -> dict:
    try:
        from ...circuit_breaker import get_breaker  # type: ignore
        cb = get_breaker()
        return {"circuit_breaker": {"state": cb.state, "failure_count": cb.failure_count}, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception:
        raise HTTPException(status_code=503, detail=api_error(EC.SERVICE_UNAVAILABLE).to_response())


@router.post("/halt")
async def halt_all_trading(
    body:  HaltRequest,
    admin: dict = Depends(_require_admin),
) -> dict:
    try:
        from ...circuit_breaker import halt_trading  # type: ignore
        await halt_trading(body.reason)
        log.warning("Trading HALTED actor=%s reason=%s", admin.get("sub"), body.reason)
        return {"halted": True, "reason": body.reason, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail=api_error(EC.INTERNAL_ERROR).to_response())


@router.post("/resume")
async def resume_all_trading(
    admin: dict = Depends(_require_admin),
) -> dict:
    try:
        from ...circuit_breaker import resume_trading  # type: ignore
        await resume_trading()
        return {"halted": False, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail=api_error(EC.INTERNAL_ERROR).to_response())


@router.get("/exposure")
async def get_exposure(user: dict = Depends(_get_current_user), orchestrator: Any = Depends(_get_orchestrator)) -> dict:
    try:
        from ...risk.exposure_control import get_exposure_control  # type: ignore
        engine   = get_exposure_control()
        snapshot = engine.get_snapshot([])
        return {"total_exposure_percent": snapshot.total_exposure_percent, "positions_by_symbol": snapshot.by_symbol, "positions_by_currency": snapshot.by_currency, "simultaneous_trades": snapshot.simultaneous_trades, "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception:
        raise HTTPException(status_code=500, detail=api_error(EC.INTERNAL_ERROR).to_response())
