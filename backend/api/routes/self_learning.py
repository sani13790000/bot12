from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..core.deps import get_current_user
from ..core.logger import get_logger

logger = get_logger("api.routes.self_learning")
router = APIRouter(tags=["Self-Learning"])


class SelfLearningStatusResponse(BaseModel):
    is_running: bool
    cycle_count: int
    last_cycle_at: Optional[str]
    next_cycle_at: Optional[str]
    model_version: int
    memory_size: int
    win_rate: float
    avg_pnl: float


class CycleResponse(BaseModel):
    cycle_id: str
    started_at: str
    completed_at: Optional[str]
    reason: str
    n_samples: int
    auc_roc: float
    accuracy: float
    improved: bool
    message: str


class ForceRetrainRequest(BaseModel):
    reason: str = Field(default="manual", description="Reason for forcing retrain")


@router.get("/status", response_model=SelfLearningStatusResponse)
async def get_status(user=Depends(get_current_user)) -> SelfLearningStatusResponse:
    """Get current self-learning service status."""
    try:
        from backend.self_learning.retraining_service import retraining_service
        s = retraining_service.get_status()
        return SelfLearningStatusResponse(**s)
    except Exception as exc:
        logger.error("[self_learning] status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/cycles", response_model=List[CycleResponse])
async def list_cycles(
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
) -> List[CycleResponse]:
    """List recent training cycles."""
    try:
        from backend.self_learning.retraining_service import retraining_service
        cycles = retraining_service.get_recent_cycles(limit=limit)
        return [CycleResponse(**c) for c in cycles]
    except Exception as exc:
        logger.error("[self_learning] cycles error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/force-retrain", response_model=CycleResponse)
async def force_retrain(
    req: ForceRetrainRequest,
    user=Depends(get_current_user),
) -> CycleResponse:
    """Force an immediate retraining cycle."""
    try:
        from backend.self_learning.retraining_service import retraining_service
        cycle = await retraining_service.force_retrain(reason=req.reason)
        return CycleResponse(**cycle)
    except Exception as exc:
        logger.error("[self_learning] force_retrain error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/start")
async def start_service(user=Depends(get_current_user)) -> Dict[str, Any]:
    """Start the self-learning background service."""
    try:
        from backend.self_learning.retraining_service import retraining_service
        await retraining_service.start()
        return {"ok": True, "message": "self-learning service started"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop")
async def stop_service(user=Depends(get_current_user)) -> Dict[str, Any]:
    """Stop the self-learning background service."""
    try:
        from backend.self_learning.retraining_service import retraining_service
        retraining_service.stop()
        return {"ok": True, "message": "self-learning service stopped"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
