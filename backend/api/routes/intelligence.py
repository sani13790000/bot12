"""
Galaxy Vast AI Trading Platform
backend/api/routes/intelligence.py -- Machine Learning Intelligence Routes
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.core.deps import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Intelligence"])


class PredictRequest(BaseModel):
    symbol: str
    timeframe: str = "H1"
    features: Dict[str, Any] = Field(default_factory=dict)


@router.post("/predict")
async def predict(
    body: PredictRequest,
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Run ML prediction for a given symbol."""
    try:
        from backend.ml.predictor import MLPredictor

        predictor = MLPredictor()
        result = await predictor.predict(
            symbol=body.symbol,
            timeframe=body.timeframe,
            features=body.features,
        )
        return {"ok": True, "prediction": result}
    except Exception as exc:
        logger.error("[Intelligence] predict error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/models")
async def list_models(
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """List available ML models and their status."""
    try:
        from backend.ml.model_registry import ModelRegistry

        registry = ModelRegistry()
        models = await registry.list_models()
        return {"ok": True, "models": models}
    except Exception as exc:
        logger.error("[Intelligence] list_models error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status")
async def get_status(
    user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get ML pipeline status."""
    return {
        "ok": True,
        "status": "operational",
        "module": "backend.ml.xgboost_trainer",
        "features": 38,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
