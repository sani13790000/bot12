from __future__ import annotations
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from ...ai_prediction import (
    PredictionService, PredictionResult, RiskLevel,
    XGBoostTrainer, DatasetBuilder, ModelManager,
    FeatureExtractor, SMCFeatures,
)
from ...ai_prediction.feature_extractor import (
    SMCSignalInput, MarketSession, TrendDirection, TradeDirection,
)
from ...core.logger import get_logger

logger = get_logger("api.routes.ai_prediction")
router = APIRouter(tags=["AI Prediction"])

_prediction_service = PredictionService()
_model_manager      = ModelManager()
_trainer            = XGBoostTrainer()


class SignalRequest(BaseModel):
    symbol:    str   = Field("XAUUSD")
    direction: str   = Field("BUY")
    entry_price: float = Field(0.0, ge=0)
    atr:         float = Field(0.0, ge=0)
    spread:      float = Field(0.0, ge=0)
    spread_ratio: float = Field(0.0, ge=0)
    volatility_ratio: float = Field(1.0, ge=0)
    bos_detected:        bool  = False
    choch_detected:      bool  = False
    bos_strength:        float = Field(0.0, ge=0, le=1)
    choch_strength:      float = Field(0.0, ge=0, le=1)
    order_block_present: bool  = False
    order_block_quality: float = Field(0.0, ge=0, le=1)
    order_block_tested:  bool  = False
    breaker_block:       bool  = False
    fvg_present:         bool  = False
    fvg_quality:         float = Field(0.0, ge=0, le=1)
    ifvg_present:        bool  = False
    liquidity_sweep:     bool  = False
    liquidity_quality:   float = Field(0.0, ge=0, le=1)
    internal_liquidity:  bool  = False
    external_liquidity:  bool  = False
    in_premium_zone:     bool  = False
    in_discount_zone:    bool  = False
    equilibrium_dist:    float = Field(0.5, ge=0, le=1)
    pa_pattern:   str   = "NONE"
    pa_quality:   float = Field(0.0, ge=0, le=1)
    pa_timeframe: str   = "M15"
    htf_alignment: bool  = False
    htf_score:     float = Field(0.0, ge=0, le=1)
    session:      str = "OFF"
    in_kill_zone: bool = False
    hour_of_day:  int  = Field(0, ge=0, le=23)
    day_of_week:  int  = Field(0, ge=0, le=4)
    decision_score: float = Field(0.0, ge=0, le=100)
    trend_direction: str  = "NEUTRAL"
    trend_strength:  float = Field(0.0, ge=0, le=1)


class PredictionResponse(BaseModel):
    probability:  int
    confidence:   int
    risk:         str
    model_auc:    float
    is_tradeable: bool
    reason:       str


class TrainRequest(BaseModel):
    exclude_rule_violations: bool = True


class TrainResponse(BaseModel):
    symbol:       str
    auc_roc:      float
    accuracy:     float
    f1_score:     float
    cv_mean:      float
    cv_std:       float
    n_estimators: int
    n_samples:    int
    is_reliable:  bool
    message:      str


class ModelInfoResponse(BaseModel):
    symbol:     str
    version:    int
    trained_at: str
    auc_roc:    float
    accuracy:   float
    f1_score:   float
    n_samples:  int
    is_best:    bool


@router.post("/predict", response_model=PredictionResponse)
def predict(request: SignalRequest) -> PredictionResponse:
    signal = _request_to_signal(request)
    result = _prediction_service.predict(signal)
    return PredictionResponse(**result.to_dict())


@router.post("/batch-predict", response_model=List[PredictionResponse])
def batch_predict(requests: List[SignalRequest]) -> List[PredictionResponse]:
    if len(requests) > 20:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="maximum 20 signals per batch request",
        )
    results = []
    for req in requests:
        signal = _request_to_signal(req)
        result = _prediction_service.predict(signal)
        results.append(PredictionResponse(**result.to_dict()))
    return results


@router.post("/train/{symbol}", response_model=TrainResponse)
def train_model(symbol: str, request: TrainRequest) -> TrainResponse:
    try:
        from ...intelligence.learning_service import learning_service
        memory = learning_service.memory
        builder = DatasetBuilder()
        dataset = builder.build(memory, exclude_rule_violations=request.exclude_rule_violations)
        result = _trainer.train(dataset)
        meta = _model_manager.save_model(
            result    = result,
            symbol    = symbol,
            n_samples = dataset.n_samples,
            win_rate  = dataset.win_rate,
        )
        _model_manager.invalidate_cache(symbol)
        return TrainResponse(
            symbol       = symbol,
            auc_roc      = round(result.auc_roc, 4),
            accuracy     = round(result.accuracy, 4),
            f1_score     = round(result.f1_score, 4),
            cv_mean      = round(result.cv_mean, 4),
            cv_std       = round(result.cv_std, 4),
            n_estimators = result.n_estimators_used,
            n_samples    = dataset.n_samples,
            is_reliable  = result.is_reliable,
            message      = f"model v{meta.version} trained successfully (AUC={result.auc_roc:.3f})",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("training failed for %s: %s", symbol, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"training failed: {e}")


@router.get("/models", response_model=List[ModelInfoResponse])
def list_models() -> List[ModelInfoResponse]:
    models = _model_manager.list_models()
    return [
        ModelInfoResponse(
            symbol=m.symbol, version=m.version, trained_at=m.trained_at,
            auc_roc=m.auc_roc, accuracy=m.accuracy, f1_score=m.f1_score,
            n_samples=m.n_samples, is_best=m.is_best,
        )
        for m in models
    ]


@router.get("/models/{symbol}", response_model=ModelInfoResponse)
def get_best_model(symbol: str) -> ModelInfoResponse:
    meta = _model_manager.get_best_metadata(symbol)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"no trained model found for symbol {symbol}")
    return ModelInfoResponse(
        symbol=meta.symbol, version=meta.version, trained_at=meta.trained_at,
        auc_roc=meta.auc_roc, accuracy=meta.accuracy, f1_score=meta.f1_score,
        n_samples=meta.n_samples, is_best=meta.is_best,
    )


@router.get("/feature-names", response_model=List[str])
def get_feature_names() -> List[str]:
    return SMCFeatures.feature_names()


def _request_to_signal(req: SignalRequest) -> SMCSignalInput:
    try:
        direction = TradeDirection(req.direction.upper())
        session   = MarketSession(req.session.upper())
        trend     = TrendDirection(req.trend_direction.upper())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return SMCSignalInput(
        symbol=req.symbol, direction=direction, entry_price=req.entry_price,
        bos_detected=req.bos_detected, choch_detected=req.choch_detected,
        bos_strength=req.bos_strength, choch_strength=req.choch_strength,
        order_block_present=req.order_block_present, order_block_quality=req.order_block_quality,
        order_block_tested=req.order_block_tested, breaker_block=req.breaker_block,
        fvg_present=req.fvg_present, fvg_quality=req.fvg_quality, ifvg_present=req.ifvg_present,
        liquidity_sweep=req.liquidity_sweep, liquidity_quality=req.liquidity_quality,
        internal_liquidity=req.internal_liquidity, external_liquidity=req.external_liquidity,
        in_premium_zone=req.in_premium_zone, in_discount_zone=req.in_discount_zone,
        equilibrium_dist=req.equilibrium_dist,
        pa_pattern=req.pa_pattern, pa_quality=req.pa_quality, pa_timeframe=req.pa_timeframe,
        atr=req.atr, spread=req.spread, spread_ratio=req.spread_ratio,
        volatility_ratio=req.volatility_ratio,
        trend_direction=trend, trend_strength=req.trend_strength,
        htf_alignment=req.htf_alignment, htf_score=req.htf_score,
        session=session, in_kill_zone=req.in_kill_zone,
        hour_of_day=req.hour_of_day, day_of_week=req.day_of_week,
        decision_score=req.decision_score,
    )
