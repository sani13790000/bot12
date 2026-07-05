"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Self-Learning API Routes
هدف: FastAPI endpoints برای مدیریت کامل Self-Learning Module

BUG-S3 FIX: Added GET /api/v1/self-learning/stats endpoint
(LearningPage.tsx was calling /stats — only /status existed before)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ...core.logger import get_logger
from ...self_learning import (
    PerformanceTracker,
    RetrainingService,
    TradeDatasetGenerator,
    TrainingPipeline,
)
from ...self_learning.trade_dataset_generator import (
    MarketConditions,
    MarketSession,
    SMCFeatures,
    TradeDirection,
    TradeRecord,
    TradeResult,
)

logger = get_logger("api.routes.self_learning")
router = APIRouter(prefix="/api/v1/self-learning", tags=["Self-Learning"])


# ─────────────────────────────────────────────────────────────────────────────
# Dependency Injection
# ─────────────────────────────────────────────────────────────────────────────

def get_dataset_generator() -> TradeDatasetGenerator:
    from ...api.main import app
    gen = getattr(app.state, "dataset_generator", None)
    if gen is None:
        raise HTTPException(status_code=503, detail="DatasetGenerator not initialized")
    return gen


def get_retraining_service() -> RetrainingService:
    from ...api.main import app
    svc = getattr(app.state, "retraining_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="RetrainingService not initialized")
    return svc


def get_performance_tracker() -> PerformanceTracker:
    from ...api.main import app
    tracker = getattr(app.state, "performance_tracker", None)
    if tracker is None:
        raise HTTPException(status_code=503, detail="PerformanceTracker not initialized")
    return tracker


# ─────────────────────────────────────────────────────────────────────────────
# BUG-S3 FIX: /stats endpoint (LearningPage.tsx was calling this — only /status existed)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats", summary="Get self-learning statistics (full metrics)")
async def get_stats(
    svc: RetrainingService = Depends(get_retraining_service),
    tracker: PerformanceTracker = Depends(get_performance_tracker),
) -> Dict[str, Any]:
    """Full retraining statistics — used by LearningPage.tsx dashboard."""
    try:
        status_data = svc.get_status()
        perf_data   = tracker.get_summary() if hasattr(tracker, "get_summary") else {}

        return {
            "total_retraining_cycles":  status_data.get("total_cycles", 0),
            "last_retrain_at":          status_data.get("last_retrain_at"),
            "last_retrain_status":      status_data.get("last_status"),
            "next_retrain_in_seconds":  status_data.get("next_retrain_in_seconds"),
            "model_version":            status_data.get("model_version"),
            "current_auc":              perf_data.get("auc"),
            "current_accuracy":         perf_data.get("accuracy"),
            "improvement_pct":          perf_data.get("improvement_pct"),
            "training_samples":         status_data.get("training_samples"),
            "is_running":               status_data.get("is_running", False),
        }
    except Exception as exc:
        logger.error("get_stats failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status", summary="Get self-learning service status")
async def get_status(
    svc: RetrainingService = Depends(get_retraining_service),
) -> Dict[str, Any]:
    """Service status — legacy endpoint."""
    return svc.get_status()


@router.post("/trigger", summary="Trigger manual retraining")
async def trigger_retraining(
    svc: RetrainingService = Depends(get_retraining_service),
) -> Dict[str, Any]:
    """Manually trigger a retraining cycle."""
    try:
        result = await svc.trigger_retrain()
        return {"triggered": True, "result": result}
    except Exception as exc:
        logger.error("trigger_retraining failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/history", summary="Get retraining history")
async def get_history(
    limit: int = Query(20, ge=1, le=100),
    svc: RetrainingService = Depends(get_retraining_service),
) -> Dict[str, Any]:
    """Return last N retraining records."""
    try:
        history = svc.get_history(limit=limit)
        return {"history": history, "count": len(history)}
    except Exception as exc:
        logger.error("get_history failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/save-trade", summary="Save a completed trade for self-learning")
async def save_trade(
    trade: Dict[str, Any],
    gen: TradeDatasetGenerator = Depends(get_dataset_generator),
) -> Dict[str, Any]:
    """Save trade outcome to the self-learning dataset."""
    try:
        saved = await gen.save_trade(trade)
        return {"saved": saved}
    except Exception as exc:
        logger.error("save_trade failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/performance", summary="Get agent performance summary")
async def get_performance(
    tracker: PerformanceTracker = Depends(get_performance_tracker),
) -> Dict[str, Any]:
    """Return performance summary from PerformanceTracker."""
    try:
        summary = tracker.get_summary() if hasattr(tracker, "get_summary") else {}
        return summary
    except Exception as exc:
        logger.error("get_performance failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
