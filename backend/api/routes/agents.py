"""
Galaxy Vast AI Trading Platform
════════════════════════════════
API Routes: Multi-Agent System
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.agents.agent_service import AgentService, get_agent_service
from backend.core.logger import get_logger

router = APIRouter(prefix="/api/v1/agents", tags=["Multi-Agent"])
logger = get_logger("api.agents")


# ── Schemas ───────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    symbol:   str   = Field(..., example="XAUUSD")
    direction: str  = Field(..., example="BUY")

    # Market Structure
    bos_detected:    bool  = False
    bos_strength:    float = 0.0
    choch_detected:  bool  = False
    choch_strength:  float = 0.0
    htf_alignment:   bool  = False
    htf_score:       float = 0.5
    structure_count: int   = 0

    # Liquidity
    liquidity_sweep:    bool  = False
    sweep_quality:      float = 0.0
    internal_liquidity: float = 0.0
    external_liquidity: float = 0.0
    in_discount_zone:   bool  = False
    in_premium_zone:    bool  = False

    # SMC
    order_block_present: bool  = False
    order_block_quality: float = 0.0
    order_block_tested:  bool  = False
    breaker_block:       bool  = False
    fvg_present:         bool  = False
    fvg_quality:         float = 0.0
    ifvg_present:        bool  = False
    in_kill_zone:        bool  = False
    session_quality:     float = 0.5

    # AI
    ai_prediction:  Dict[str, Any] = Field(default_factory=dict)
    decision_score: float = 50.0

    # Risk
    portfolio_risk_percent: float = 0.0
    spread_ratio:           float = 1.0
    atr_normalized:         float = 1.0
    daily_trades_count:     int   = 0
    max_daily_trades:       int   = 5
    daily_loss_percent:     float = 0.0
    max_daily_loss_percent: float = 3.0
    consecutive_losses:     int   = 0

    # News
    news_filter_enabled: bool = True
    upcoming_news:       List[Dict[str, Any]] = Field(default_factory=list)

    # Execution
    trading_mode:           str   = "FULL_AUTO"
    session:                str   = "LONDON"
    expected_slippage_pips: float = 0.0
    market_depth_score:     float = 0.7


class UpdateWeightsRequest(BaseModel):
    weights: Dict[str, float] = Field(
        ...,
        example={
            "Market Structure": 0.20,
            "Liquidity":        0.15,
            "SMC":              0.20,
            "AI Prediction":    0.20,
            "Risk":             0.15,
            "News":             0.10,
            "Execution":        0.10,
        }
    )


class SetThresholdRequest(BaseModel):
    threshold: float = Field(..., ge=0.0, le=100.0, example=65.0)


class AgentControlRequest(BaseModel):
    agent_name: str  = Field(..., example="News")
    enabled:    bool = True


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/evaluate", summary="اجرای Multi-Agent و دریافت رأی نهایی")
async def evaluate(
    req:     EvaluateRequest,
    service: AgentService = Depends(get_agent_service),
) -> Dict[str, Any]:
    """
    اجرای همه ۷ Agent به صورت موازی و بازگشت رأی نهایی.

    خروجی:
    - decision: BUY / SELL / NO_TRADE / BLOCKED
    - final_score: امتیاز وزن‌دار نهایی (0–100)
    - final_confidence: اطمینان میانگین (0–100)
    - votes: رأی هر Agent به صورت جداگانه
    """
    try:
        context = req.model_dump()
        result  = await service.evaluate(context)
        return {
            "success": True,
            "data":    result.to_dict(),
        }
    except Exception as exc:
        logger.error(f"Evaluate error: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=str(exc))


@router.get("/weights", summary="وزن‌های فعلی Agentها")
async def get_weights(service: AgentService = Depends(get_agent_service)) -> Dict[str, Any]:
    return {"success": True, "data": service.get_agent_weights()}


@router.put("/weights", summary="بروزرسانی وزن‌های Agentها")
async def update_weights(
    req:     UpdateWeightsRequest,
    service: AgentService = Depends(get_agent_service),
) -> Dict[str, Any]:
    service.update_weights(req.weights)
    return {"success": True, "data": service.get_agent_weights()}


@router.put("/threshold", summary="تغییر آستانه تصمیم‌گیری")
async def set_threshold(
    req:     SetThresholdRequest,
    service: AgentService = Depends(get_agent_service),
) -> Dict[str, Any]:
    service.set_threshold(req.threshold)
    return {"success": True, "threshold": req.threshold}


@router.put("/control", summary="فعال/غیرفعال کردن Agent")
async def control_agent(
    req:     AgentControlRequest,
    service: AgentService = Depends(get_agent_service),
) -> Dict[str, Any]:
    if req.enabled:
        service.enable_agent(req.agent_name)
    else:
        service.disable_agent(req.agent_name)
    return {"success": True, "agent": req.agent_name, "enabled": req.enabled}


@router.get("/list", summary="لیست همه Agentها")
async def list_agents(service: AgentService = Depends(get_agent_service)) -> Dict[str, Any]:
    weights = service.get_agent_weights()
    return {
        "success": True,
        "data": [
            {"name": name, "weight": weight}
            for name, weight in weights.items()
        ],
    }
