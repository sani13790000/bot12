"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Intelligence API Routes
هدف: آموزش مداوم مدل XGBoost، ذخیره وزن‌های Learning و Prediction API
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.core.deps import get_current_user

log = logging.getLogger(__name__)
router = APIRouter(tags=["Intelligence — یادگیری ماشین"])


# ── models ──────────────────────────────────────────────────────────────────────────────

class TradeOutcomeInput(BaseModel):
    trade_id:       str
    symbol:         str
    direction:      str
    entry_price:    float
    exit_price:     float
    stop_loss:      float
    take_profit:    float
    pnl:            float
    duration_hours: float = 0.0
    rr_achieved:    float = 0.0
    confidence:     float = Field(default=0.0, ge=0.0, le=100.0)


class PredictRequest(BaseModel):
    symbol:         str
    direction:      str
    entry_price:    float
    stop_loss:      float
    take_profit:    float
    confidence:     float = Field(default=0.0, ge=0.0, le=100.0)
    market_session: str   = "LONDON"
    volatility:     float = 0.0
    spread_pips:    float = 0.0


class WeightsResponse(BaseModel):
    weights: Dict[str, float]
    version: int
    updated_at: Optional[str]


# ── helpers ─────────────────────────────────────────────────────────────────────────────

def _get_ml_pipeline():
    from backend.self_learning.xgboost_trainer import XGBoostTrainer
    return XGBoostTrainer()


def _get_db():
    from backend.database.connection import get_db_client
    return get_db_client()


# ── endpoints ──────────────────────────────────────────────────────────────────────

@router.post("/record-trade", status_code=status.HTTP_201_CREATED)
async def record_trade_outcome(
    payload: TradeOutcomeInput,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Record a completed trade for continuous ML retraining."""
    try:
        db = _get_db()
        from datetime import datetime, timezone
        row = {
            **payload.model_dump(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        resp = db.table("ml_training_data").insert(row).execute()
        return {"ok": True, "id": resp.data[0].get("id") if resp.data else None}
    except Exception as exc:
        log.error("intelligence/record-trade error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/predict")
async def predict_outcome(
    req: PredictRequest,
    _user=Depends(get_current_user),
) -> Dict[str, Any]:
    """Predict trade outcome probability using XGBoost model."""
    try:
        ml = _get_ml_pipeline()
        features = {
            "symbol":         req.symbol,
            "direction":      req.direction,
            "entry_price":    req.entry_price,
            "stop_loss":      req.stop_loss,
            "take_profit":    req.take_profit,
            "confidence":     req.confidence,
            "market_session": req.market_session,
            "volatility":     req.volatility,
            "spread_pips":    req.spread_pips,
        }
        result = await ml.predict(features)
        return {
            "ok":              True,
            "win_probability": round(result.get("win_prob", 0.0), 4),
            "confidence":      round(result.get("confidence", 0.0), 4),
            "model_version":   result.get("model_version", "unknown"),
        }
    except Exception as exc:
        log.error("intelligence/predict error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/weights", response_model=WeightsResponse)
async def get_weights(_user=Depends(get_current_user)) -> Dict[str, Any]:
    """Get current ML model feature weights."""
    try:
        ml = _get_ml_pipeline()
        weights = await ml.get_feature_weights()
        return {
            "weights":    weights.get("weights", {}),
            "version":    weights.get("version", 0),
            "updated_at": weights.get("updated_at"),
        }
    except Exception as exc:
        log.error("intelligence/weights error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/retrain")
async def trigger_retrain(_user=Depends(get_current_user)) -> Dict[str, Any]:
    """Manually trigger XGBoost model retraining."""
    try:
        from backend.self_learning.retraining_service import retraining_service
        await retraining_service.trigger_now()
        return {"ok": True, "message": "Retraining triggered"}
    except Exception as exc:
        log.error("intelligence/retrain error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/status")
async def get_intelligence_status(_user=Depends(get_current_user)) -> Dict[str, Any]:
    """Get ML pipeline status and statistics."""
    try:
        db = _get_db()
        resp = db.table("ml_training_data").select("id", count="exact").execute()
        total_samples = resp.count or 0
        return {
            "ok":            True,
            "total_samples": total_samples,
            "model":         "xgboost_v1",
            "status":        "active",
        }
    except Exception as exc:
        log.error("intelligence/status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
