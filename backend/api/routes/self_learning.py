"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ماژول: Self-Learning API Routes
هدف: FastAPI endpoints برای مدیریت کامل Self-Learning Module
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
# Dependency Injection (در main.py به app.state وصل می‌شود)
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
# Request / Response Models
# ─────────────────────────────────────────────────────────────────────────────

class SMCFeaturesIn(BaseModel):
    bos_detected:         bool  = False
    bos_strength:         float = Field(0.0, ge=0.0, le=1.0)
    choch_detected:       bool  = False
    choch_strength:       float = Field(0.0, ge=0.0, le=1.0)
    order_block_present:  bool  = False
    order_block_quality:  float = Field(0.0, ge=0.0, le=1.0)
    order_block_tested:   bool  = False
    breaker_block:        bool  = False
    fvg_present:          bool  = False
    fvg_quality:          float = Field(0.0, ge=0.0, le=1.0)
    ifvg_present:         bool  = False
    liquidity_sweep:      bool  = False
    sweep_quality:        float = Field(0.0, ge=0.0, le=1.0)
    internal_liquidity:   bool  = False
    external_liquidity:   bool  = False
    in_premium_zone:      bool  = False
    in_discount_zone:     bool  = False
    equilibrium_distance: float = 0.0
    structure_score:      float = Field(0.0, ge=0.0, le=1.0)


class MarketConditionsIn(BaseModel):
    symbol:           str   = "XAUUSD"
    session:          str   = "OFF"
    in_kill_zone:     bool  = False
    atr_value:        float = 0.0
    atr_normalized:   float = 0.0
    spread_pips:      float = 0.0
    spread_ratio:     float = 0.0
    volatility_ratio: float = 1.0
    trend_direction:  int   = 0
    trend_strength:   float = 0.0
    htf_alignment:    bool  = False
    htf_score:        float = 0.0
    hour_of_day:      int   = Field(0, ge=0, le=23)
    day_of_week:      int   = Field(0, ge=0, le=6)
    news_active:      bool  = False


class SaveTradeRequest(BaseModel):
    mt5_ticket:       int   = 0
    symbol:           str   = "XAUUSD"
    direction:        str   = Field(..., pattern="^(BUY|SELL)$")
    result:           str   = Field(..., pattern="^(WIN|LOSS|BE)$")
    entry_price:      float
    exit_price:       float
    stop_loss:        float = 0.0
    take_profit:      float = 0.0
    lot_size:         float = Field(0.01, gt=0)
    profit_loss:      float = 0.0
    profit_pips:      float = 0.0
    risk_reward_actual: float = 0.0
    entry_time:       datetime
    exit_time:        datetime
    confidence_score: float = Field(0.0, ge=0.0, le=100.0)
    decision_score:   float = Field(0.0, ge=0.0, le=100.0)
    smc:              SMCFeaturesIn       = Field(default_factory=SMCFeaturesIn)
    market:           MarketConditionsIn  = Field(default_factory=MarketConditionsIn)
    model_version:    str  = "unknown"
    is_rule_violation: bool = False
    violation_reason: str  = ""


class RetrainRequest(BaseModel):
    symbol: str = "XAUUSD"
    force:  bool = False
    reason: str  = "manual"


class RollbackRequest(BaseModel):
    symbol: str


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/trades", summary="ذخیره معامله بسته‌شده")
async def save_closed_trade(
    body: SaveTradeRequest,
    gen:  TradeDatasetGenerator = Depends(get_dataset_generator),
) -> Dict[str, Any]:
    """
    ذخیره یک معامله کامل‌شده در PostgreSQL برای Self-Learning.

    هر بار که MT5 یک معامله را می‌بندد باید این endpoint فراخوانی شود.
    """
    try:
        smc = SMCFeatures(
            bos_detected         = body.smc.bos_detected,
            bos_strength         = body.smc.bos_strength,
            choch_detected       = body.smc.choch_detected,
            choch_strength       = body.smc.choch_strength,
            order_block_present  = body.smc.order_block_present,
            order_block_quality  = body.smc.order_block_quality,
            order_block_tested   = body.smc.order_block_tested,
            breaker_block        = body.smc.breaker_block,
            fvg_present          = body.smc.fvg_present,
            fvg_quality          = body.smc.fvg_quality,
            ifvg_present         = body.smc.ifvg_present,
            liquidity_sweep      = body.smc.liquidity_sweep,
            sweep_quality        = body.smc.sweep_quality,
            internal_liquidity   = body.smc.internal_liquidity,
            external_liquidity   = body.smc.external_liquidity,
            in_premium_zone      = body.smc.in_premium_zone,
            in_discount_zone     = body.smc.in_discount_zone,
            equilibrium_distance = body.smc.equilibrium_distance,
            structure_score      = body.smc.structure_score,
        )
        market = MarketConditions(
            symbol           = body.market.symbol,
            session          = MarketSession(body.market.session),
            in_kill_zone     = body.market.in_kill_zone,
            atr_value        = body.market.atr_value,
            atr_normalized   = body.market.atr_normalized,
            spread_pips      = body.market.spread_pips,
            spread_ratio     = body.market.spread_ratio,
            volatility_ratio = body.market.volatility_ratio,
            trend_direction  = body.market.trend_direction,
            trend_strength   = body.market.trend_strength,
            htf_alignment    = body.market.htf_alignment,
            htf_score        = body.market.htf_score,
            hour_of_day      = body.market.hour_of_day,
            day_of_week      = body.market.day_of_week,
            news_active      = body.market.news_active,
        )
        duration = int((body.exit_time - body.entry_time).total_seconds() / 60)
        record = TradeRecord(
            mt5_ticket          = body.mt5_ticket,
            symbol              = body.symbol,
            direction           = TradeDirection(body.direction),
            result              = TradeResult(body.result),
            entry_price         = body.entry_price,
            exit_price          = body.exit_price,
            stop_loss           = body.stop_loss,
            take_profit         = body.take_profit,
            lot_size            = body.lot_size,
            profit_loss         = body.profit_loss,
            profit_pips         = body.profit_pips,
            risk_reward_actual  = body.risk_reward_actual,
            entry_time          = body.entry_time,
            exit_time           = body.exit_time,
            duration_minutes    = duration,
            confidence_score    = body.confidence_score,
            decision_score      = body.decision_score,
            smc                 = smc,
            market              = market,
            model_version       = body.model_version,
            is_rule_violation   = body.is_rule_violation,
            violation_reason    = body.violation_reason,
        )
        trade_id = await gen.save_trade(record)
        return {"success": True, "trade_id": trade_id, "symbol": body.symbol, "result": body.result}

    except Exception as exc:
        logger.error(f"save_closed_trade error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trades/statistics", summary="آمار معاملات ذخیره‌شده")
async def get_trade_statistics(
    symbol: Optional[str]      = Query(None),
    gen:    TradeDatasetGenerator = Depends(get_dataset_generator),
) -> Dict[str, Any]:
    return await gen.get_statistics(symbol=symbol)


@router.get("/trades/count", summary="تعداد معاملات")
async def get_trade_count(
    symbol:     Optional[str] = Query(None),
    valid_only: bool          = Query(True),
    gen:        TradeDatasetGenerator = Depends(get_dataset_generator),
) -> Dict[str, Any]:
    count = await gen.count_trades(symbol=symbol, valid_only=valid_only)
    return {"count": count, "symbol": symbol or "ALL", "valid_only": valid_only}


@router.post("/retrain", summary="اجرای بازآموزی")
async def trigger_retraining(
    body: RetrainRequest,
    svc:  RetrainingService = Depends(get_retraining_service),
) -> Dict[str, Any]:
    """اجرای دستی یک چرخه بازآموزی برای یک نماد."""
    job = await svc.retrain_symbol(symbol=body.symbol, reason=body.reason, force=body.force)
    return job.to_dict()


@router.post("/rollback", summary="rollback به مدل قبلی")
async def rollback_model(
    body: RollbackRequest,
    svc:  RetrainingService = Depends(get_retraining_service),
) -> Dict[str, Any]:
    success = await svc.rollback(symbol=body.symbol)
    if not success:
        raise HTTPException(status_code=404, detail=f"No previous model for {body.symbol}")
    return {"success": True, "symbol": body.symbol, "message": "Rollback successful"}


@router.get("/status", summary="وضعیت کلی سرویس")
async def get_service_status(
    svc: RetrainingService = Depends(get_retraining_service),
) -> Dict[str, Any]:
    return await svc.get_status()


@router.get("/jobs", summary="تاریخچه چرخه‌های بازآموزی")
async def get_job_history(
    symbol: Optional[str] = Query(None),
    limit:  int           = Query(20, ge=1, le=100),
    svc:    RetrainingService = Depends(get_retraining_service),
) -> List[Dict[str, Any]]:
    return svc.get_job_history(symbol=symbol, limit=limit)


@router.get("/models/{symbol}", summary="تاریخچه مدل‌های یک نماد")
async def get_model_history(
    symbol:  str,
    limit:   int              = Query(10, ge=1, le=50),
    tracker: PerformanceTracker = Depends(get_performance_tracker),
) -> List[Dict[str, Any]]:
    return await tracker.get_model_history(symbol=symbol, limit=limit)


@router.get("/models/{symbol}/compare", summary="مقایسه نسخه‌های مدل")
async def compare_model_versions(
    symbol:  str,
    tracker: PerformanceTracker = Depends(get_performance_tracker),
) -> Dict[str, Any]:
    return await tracker.compare_versions(symbol=symbol)


@router.get("/models/summary/all", summary="خلاصه همه مدل‌های فعال")
async def get_all_models_summary(
    tracker: PerformanceTracker = Depends(get_performance_tracker),
) -> List[Dict[str, Any]]:
    return await tracker.get_all_symbols_summary()
