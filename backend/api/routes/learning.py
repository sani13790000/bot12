from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
# BUG-AF4 FIX: removed prefix="/learning" -- double prefix was causing /learning/learning/*
router = APIRouter(tags=["Self-Learning"])


class TradeOutcomeRequest(BaseModel):
    signal_id:    str
    symbol:       str
    direction:    str
    entry_price:  float
    exit_price:   float
    pnl:          float
    smc_features: Optional[Dict[str, Any]] = None


class RetrainRequest(BaseModel):
    reason: str = Field("manual")


@router.get("/status")
async def get_learning_status() -> Dict[str, Any]:
    try:
        from backend.intelligence.learning_service import get_learning_service
        svc = get_learning_service()
        return {"ok": True, "status": svc.get_status()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cycles")
async def get_learning_cycles() -> Dict[str, Any]:
    try:
        from backend.intelligence.learning_service import get_learning_service
        return {"ok": True, "cycles": get_learning_service().get_cycles()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/retrain")
async def force_retrain(req: RetrainRequest) -> Dict[str, Any]:
    try:
        from backend.intelligence.learning_service import get_learning_service
        cycle = await get_learning_service().force_retrain(reason=req.reason)
        return {"ok": True, "cycle": cycle.to_dict()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/record-outcome")
async def record_outcome(req: TradeOutcomeRequest) -> Dict[str, Any]:
    try:
        from backend.intelligence.learning_service import get_learning_service
        await get_learning_service().record_trade_outcome(req.model_dump())
        return {"ok": True, "message": "outcome recorded"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/initialize")
async def initialize_learning() -> Dict[str, Any]:
    try:
        from backend.intelligence.learning_service import get_learning_service
        await get_learning_service().initialize()
        return {"ok": True, "message": "initialized"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
