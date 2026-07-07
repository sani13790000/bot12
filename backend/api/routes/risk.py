"""
backend/api/routes/risk.py
Galaxy Vast AI Trading Platform — Risk API Routes
"""

from __future__ import annotations

import datetime
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...circuit_breaker import get_breaker, halt_trading, resume_trading
from ...core.deps import get_risk_orchestrator_dep
from ...core.logger import get_logger

router = APIRouter()
logger = get_logger("api.routes.risk")


# ── Request / Response models ─────────────────────────────────────────────────


class RiskAssessRequest(BaseModel):
    signal_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=3, max_length=12)
    direction: str = Field(..., pattern="^(BUY|SELL)$")
    balance: float = Field(..., gt=0)
    equity: float = Field(..., gt=0)
    stop_loss_pips: float = Field(default=20.0, gt=0)
    risk_percent: float = Field(default=1.0, gt=0, le=10)
    open_positions: list = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RiskAssessResponse(BaseModel):
    approved: bool
    reason: str = ""
    lot_size: float = 0.0
    risk_percent: float = 1.0
    gate_results: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0.0


class HaltRequest(BaseModel):
    reason: str = Field(default="manual_halt", min_length=1)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/assess",
    response_model=RiskAssessResponse,
    summary="Assess risk for a trading signal",
)
async def assess_risk(
    body: RiskAssessRequest,
    orchestrator: Any = Depends(get_risk_orchestrator_dep),
) -> RiskAssessResponse:
    """Run the full risk pipeline (7 gates) and return a decision."""
    try:
        from ...risk.risk_orchestrator import RiskInput

        inp = RiskInput(
            signal_id=body.signal_id,
            symbol=body.symbol,
            direction=body.direction,
            balance=body.balance,
            equity=body.equity,
            stop_loss_pips=body.stop_loss_pips,
            risk_percent=body.risk_percent,
            open_positions=body.open_positions,
            metadata=body.metadata,
        )
        decision = await orchestrator.assess(inp)
        return RiskAssessResponse(**decision.to_dict())
    except Exception as exc:
        logger.error("assess_risk failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "RISK_ASSESS_ERROR", "message": str(exc)},
        )


@router.get("/status", summary="Risk system status")
async def risk_status() -> Dict[str, Any]:
    """Return current risk system health."""
    try:
        cb = get_breaker()
        return {
            "circuit_breaker": {
                "state": cb.state,
                "failure_count": cb.failure_count,
                "last_failure": str(cb.last_failure_time) if cb.last_failure_time else None,
            },
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("risk_status failed", error=str(exc))
        return {"error": str(exc), "timestamp": datetime.datetime.utcnow().isoformat()}


@router.post("/halt", summary="Halt all trading (circuit breaker)")
async def halt_all_trading(body: HaltRequest) -> Dict[str, Any]:
    """Activate circuit breaker — stops all new trades."""
    try:
        await halt_trading(body.reason)
        logger.warning("Trading HALTED via API", reason=body.reason)
        return {
            "halted": True,
            "reason": body.reason,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("halt_trading failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/resume", summary="Resume trading (circuit breaker)")
async def resume_all_trading() -> Dict[str, Any]:
    """Deactivate circuit breaker — resumes normal trading."""
    try:
        await resume_trading()
        logger.info("Trading RESUMED via API")
        return {"halted": False, "timestamp": datetime.datetime.utcnow().isoformat()}
    except Exception as exc:
        logger.error("resume_trading failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/exposure", summary="Current exposure snapshot")
async def get_exposure(
    orchestrator: Any = Depends(get_risk_orchestrator_dep),
) -> Dict[str, Any]:
    """Return current portfolio exposure via ExposureControl gate."""
    try:
        from ...risk.exposure_control import get_exposure_control

        engine = get_exposure_control()
        snapshot = engine.get_snapshot([])
        return {
            "total_exposure_percent": snapshot.total_exposure_percent,
            "positions_by_symbol": snapshot.by_symbol,
            "positions_by_currency": snapshot.by_currency,
            "simultaneous_trades": snapshot.simultaneous_trades,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("get_exposure failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
