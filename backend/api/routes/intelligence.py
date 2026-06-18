"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Intelligence API Routes

Endpoints:
  POST /intelligence/record-trade    ← ثبت معامله در Learning Service
  POST /intelligence/predict         ← پیش‌بینی کیفیت سیگنال با ML
  GET  /intelligence/weights         ← وزن‌های فعلی Decision Engine
  GET  /intelligence/memory/stats    ← آمار حافظه معاملاتی
  POST /intelligence/learn           ← اجرای چرخه کامل یادگیری
  GET  /intelligence/failure-report  ← گزارش تحلیل شکست‌ها
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...intelligence import (
    TradeMemory, TradeContext, TradeOutcome,
    FailureAnalyzer, FailureReport,
    MLEngine, MLPrediction,
    WeightAdjuster, WeightUpdate,
)
from ...intelligence.trade_memory import (
    SMCContext, PAContext, RiskContext,
    MarketSession, MarketCondition,
)
from ...intelligence.learning_service import LearningService, LearningCycleResult
from ...core.logger import get_logger

logger = get_logger("api.routes.intelligence")
router = APIRouter(prefix="/intelligence", tags=["Intelligence — یادگیری ماشین"])

# ─── Singleton LearningService ──────────────────────────────────
_learning_service: Optional[LearningService] = None


def get_learning_service() -> LearningService:
    """Dependency Injection برای LearningService"""
    global _learning_service
    if _learning_service is None:
        _learning_service = LearningService(model_dir="models")
    return _learning_service


# ─── Pydantic Schemas ───────────────────────────────────────────

class SMCContextRequest(BaseModel):
    bos_detected: bool = False
    choch_detected: bool = False
    order_block_quality: float = Field(0.0, ge=0, le=1)
    fvg_quality: float = Field(0.0, ge=0, le=1)
    liquidity_swept: bool = False
    in_premium_zone: bool = False
    in_discount_zone: bool = False
    kill_zone_active: bool = False
    structure_score: float = Field(0.0, ge=0, le=1)
    htf_alignment: float = Field(0.0, ge=0, le=1)


class PAContextRequest(BaseModel):
    primary_pattern: str = ""
    pattern_quality: float = Field(0.0, ge=0, le=1)
    confirmation_patterns: List[str] = []
    rejection_strength: float = Field(0.0, ge=0, le=1)
    momentum_alignment: bool = False


class RiskContextRequest(BaseModel):
    lot_size: float = Field(0.0, ge=0)
    risk_percent: float = Field(0.0, ge=0, le=100)
    stop_loss_pips: float = Field(0.0, ge=0)
    take_profit_pips: float = Field(0.0, ge=0)
    risk_reward_ratio: float = Field(0.0, ge=0)
    portfolio_risk_at_entry: float = Field(0.0, ge=0, le=100)
    atr_at_entry: float = Field(0.0, ge=0)
    spread_at_entry: float = Field(0.0, ge=0)


class RecordTradeRequest(BaseModel):
    signal_id: str = ""
    symbol: str = Field(..., min_length=1, max_length=20)
    entry_time: datetime
    exit_time: Optional[datetime] = None
    duration_minutes: float = Field(0.0, ge=0)
    entry_price: float = Field(..., gt=0)
    exit_price: float = Field(0.0, ge=0)
    stop_loss: float = Field(0.0, ge=0)
    take_profit: float = Field(0.0, ge=0)
    direction: str = Field(..., pattern="^(BUY|SELL)$")
    outcome: str = Field(..., pattern="^(WIN|LOSS|BE|PARTIAL)$")
    pnl_pips: float = 0.0
    pnl_usd: float = 0.0
    realized_rr: float = 0.0
    confidence_score: float = Field(0.0, ge=0, le=100)
    session: str = "OFF_HOURS"
    market_condition: str = "RANGING"
    smc: SMCContextRequest = SMCContextRequest()
    price_action: PAContextRequest = PAContextRequest()
    risk: RiskContextRequest = RiskContextRequest()
    news_active: bool = False
    previous_consecutive_losses: int = Field(0, ge=0)


class PredictRequest(BaseModel):
    """feature vector برای پیش‌بینی ML"""
    features: Dict[str, float] = Field(
        ...,
        description="feature vector از TradeContext.to_ml_features()"
    )


class WeightsResponse(BaseModel):
    smc_weight: float
    price_action_weight: float
    htf_alignment_weight: float
    session_weight: float
    ltf_weight: float
    bos_weight: float
    order_block_weight: float
    fvg_weight: float
    liquidity_weight: float
    structure_weight: float


# ─── Endpoints ──────────────────────────────────────────────────

@router.post("/record-trade", status_code=status.HTTP_201_CREATED)
async def record_trade(
    request: RecordTradeRequest,
    service: LearningService = Depends(get_learning_service),
) -> Dict[str, Any]:
    """
    ثبت معامله در سیستم یادگیری.
    بعد از ثبت، چرخه‌های یادگیری در پس‌زمینه اجرا می‌شوند.
    """
    # ساخت TradeContext
    context = TradeContext(
        signal_id=request.signal_id,
        symbol=request.symbol,
        entry_time=request.entry_time,
        exit_time=request.exit_time,
        duration_minutes=request.duration_minutes,
        entry_price=request.entry_price,
        exit_price=request.exit_price,
        stop_loss=request.stop_loss,
        take_profit=request.take_profit,
        direction=request.direction,
        outcome=TradeOutcome(request.outcome),
        pnl_pips=request.pnl_pips,
        pnl_usd=request.pnl_usd,
        realized_rr=request.realized_rr,
        confidence_score=request.confidence_score,
        session=MarketSession(request.session),
        market_condition=MarketCondition(request.market_condition),
        smc=SMCContext(**request.smc.model_dump()),
        price_action=PAContext(**request.price_action.model_dump()),
        risk=RiskContext(**request.risk.model_dump()),
        news_active=request.news_active,
        previous_consecutive_losses=request.previous_consecutive_losses,
    )

    failure_report = await service.record_trade(context)

    response: Dict[str, Any] = {
        "trade_id": context.trade_id,
        "recorded": True,
        "outcome": context.outcome.value,
    }

    if failure_report:
        response["failure_analysis"] = {
            "is_valid_loss": failure_report.is_valid_loss,
            "severity": failure_report.severity,
            "rule_violations_count": len(failure_report.rule_violations),
            "failure_types": [ft.value for ft in failure_report.failure_types],
            "summary": failure_report.summary,
        }

    return response


@router.post("/predict")
async def predict_signal_quality(
    request: PredictRequest,
    service: LearningService = Depends(get_learning_service),
) -> Dict[str, Any]:
    """
    پیش‌بینی کیفیت سیگنال با مدل ML.
    """
    prediction = await service.predict_signal_quality(request.features)
    return {
        "win_probability": round(prediction.win_probability, 4),
        "confidence": round(prediction.confidence, 4),
        "adjusted_score": round(prediction.adjusted_score, 4),
        "recommendation": prediction.recommendation,
        "is_reliable": prediction.is_reliable,
        "training_samples": prediction.training_samples,
        "model_type": prediction.model_type.value,
        "top_features": dict(
            sorted(
                prediction.feature_importances.items(),
                key=lambda x: x[1], reverse=True
            )[:5]
        ),
    }


@router.get("/weights", response_model=WeightsResponse)
async def get_current_weights(
    service: LearningService = Depends(get_learning_service),
) -> WeightsResponse:
    """وزن‌های فعلی Decision Engine"""
    w = service.get_current_weights()
    return WeightsResponse(**w.to_dict())


@router.get("/memory/stats")
async def get_memory_stats(
    service: LearningService = Depends(get_learning_service),
) -> Dict[str, Any]:
    """آمار حافظه معاملاتی"""
    return service.get_memory_stats()


@router.post("/learn")
async def run_learning_cycle(
    service: LearningService = Depends(get_learning_service),
) -> Dict[str, Any]:
    """
    اجرای چرخه کامل یادگیری به صورت دستی.
    برای استفاده از dashboard یا telegram.
    """
    result = await service.run_full_learning_cycle()
    return {
        "timestamp": result.timestamp.isoformat(),
        "trades_analyzed": result.trades_analyzed,
        "failure_reports": result.failure_reports,
        "valid_losses": result.valid_losses,
        "rule_violations": result.rule_violations,
        "ml_retrained": result.ml_retrained,
        "weights_adjusted": result.weights_adjusted,
        "weight_updates": [
            {
                "factor": u.factor,
                "old": round(u.old_weight, 4),
                "new": round(u.new_weight, 4),
                "delta": round(u.delta, 4),
                "reason": u.reason,
            }
            for u in result.weight_updates
        ],
        "top_violations": result.top_violation_types,
        "summary": result.summary,
    }
