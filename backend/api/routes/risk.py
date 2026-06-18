"""
Galaxy Vast AI Trading Platform
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Risk Management API Routes — 10 endpoints
"""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional

from ...risk.risk_orchestrator  import get_risk_orchestrator, RiskInput
from ...risk.exposure_control   import ExposurePosition
from ...risk.lot_sizing         import LotSizingMethod, get_lot_sizer
from ...risk.equity_protection  import get_equity_protection
from ...risk.volatility_filter  import get_volatility_filter
from ...risk.correlation_filter import get_correlation_filter

router = APIRouter(prefix="/api/v1/risk", tags=["Risk Management"])


# ── Request / Response Models ────────────────────────────────────

class OpenPositionIn(BaseModel):
    symbol: str
    direction: str
    risk_percent: float
    risk_usd: float = 0.0

class RiskAssessRequest(BaseModel):
    symbol: str
    direction: str = Field(..., pattern="^(BUY|SELL)$")
    balance: float
    equity: float
    stop_loss_pips: float
    current_atr: float
    atr_history: List[float] = []
    current_spread: float = 0.0
    avg_spread: float = 0.0
    open_positions: List[OpenPositionIn] = []
    today_trades_count: int = 0
    today_pnl_usd: float = 0.0
    week_pnl_usd: float = 0.0
    month_pnl_usd: float = 0.0
    win_rate: float = 0.55
    avg_rr: float = 1.5

class LotSizeRequest(BaseModel):
    balance: float
    stop_loss_pips: float
    atr_pips: Optional[float] = None
    method: str = "ATR_BASED"
    win_rate: float = 0.55
    avg_rr: float = 1.5
    volatility_ratio: float = 1.0

class TradeResultRequest(BaseModel):
    pnl_usd: float
    balance: float

class EquityUpdateRequest(BaseModel):
    current_equity: float
    current_balance: float

class CorrelationCheckRequest(BaseModel):
    symbol_a: str
    symbol_b: str

class LotSizingConfigUpdate(BaseModel):
    method: Optional[str] = None
    risk_percent: Optional[float] = None
    max_risk_percent: Optional[float] = None
    atr_multiplier: Optional[float] = None
    min_lot: Optional[float] = None
    max_lot: Optional[float] = None


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/assess")
async def assess_risk(req: RiskAssessRequest):
    """
    Master risk assessment — runs ALL 5 gates:
    Equity → Daily Limits → Volatility → Correlation → Exposure
    Returns lot size + full audit trail.
    """
    orchestrator = get_risk_orchestrator()
    positions = [
        ExposurePosition(symbol=p.symbol, direction=p.direction,
                         risk_percent=p.risk_percent, risk_usd=p.risk_usd)
        for p in req.open_positions
    ]
    inp = RiskInput(
        symbol=req.symbol, direction=req.direction,
        balance=req.balance, equity=req.equity,
        stop_loss_pips=req.stop_loss_pips,
        current_atr=req.current_atr, atr_history=req.atr_history,
        current_spread=req.current_spread, avg_spread=req.avg_spread,
        open_positions=positions,
        today_trades_count=req.today_trades_count,
        today_pnl_usd=req.today_pnl_usd,
        week_pnl_usd=req.week_pnl_usd,
        month_pnl_usd=req.month_pnl_usd,
        win_rate=req.win_rate, avg_rr=req.avg_rr,
    )
    decision = orchestrator.assess(inp)
    return decision.to_dict()


@router.post("/lot-size")
async def calculate_lot_size(req: LotSizeRequest):
    """Calculate optimal lot size using configured method."""
    try:
        method = LotSizingMethod(req.method)
    except ValueError:
        raise HTTPException(400, f"Invalid method: {req.method}")

    sizer = get_lot_sizer()
    sizer.update_config(method=method)
    result = sizer.calculate(
        balance=req.balance,
        stop_loss_pips=req.stop_loss_pips,
        atr_pips=req.atr_pips,
        win_rate=req.win_rate,
        avg_rr=req.avg_rr,
        volatility_ratio=req.volatility_ratio,
    )
    return {
        "lot_size": result.lot_size,
        "method": result.method_used.value,
        "risk_usd": result.risk_amount_usd,
        "risk_percent": result.risk_percent,
        "stop_loss_pips": result.stop_loss_pips,
        "notes": result.notes,
    }


@router.post("/record-trade")
async def record_trade_result(req: TradeResultRequest):
    """Record closed trade P&L — updates equity protection state."""
    orchestrator = get_risk_orchestrator()
    orchestrator.record_trade_result(req.pnl_usd, req.balance)
    equity = get_equity_protection()
    state = equity.state
    return {
        "recorded": True,
        "consecutive_losses": state.consecutive_losses,
        "daily_loss_usd": round(state.daily_loss_usd, 2),
        "protection_level": state.protection_level.value,
    }


@router.post("/equity/update")
async def update_equity(req: EquityUpdateRequest):
    """Update live equity — triggers drawdown recalculation."""
    engine = get_equity_protection()
    result = engine.update_equity(req.current_equity, req.current_balance)
    return {
        "can_trade": result.can_trade,
        "level": result.level.value,
        "reason": result.reason,
        "drawdown_percent": round(result.drawdown_percent, 2),
        "consecutive_losses": result.consecutive_losses,
        "daily_loss_percent": round(result.daily_loss_percent, 2),
        "should_close_all": result.should_close_all,
        "cooldown_remaining_minutes": result.cooldown_remaining_minutes,
    }


@router.get("/equity/state")
async def get_equity_state():
    """Get current equity protection state."""
    engine = get_equity_protection()
    s = engine.state
    return {
        "balance": s.balance,
        "equity": s.equity,
        "high_water_mark": s.high_water_mark,
        "drawdown_percent": round(s.current_drawdown_percent, 2),
        "consecutive_losses": s.consecutive_losses,
        "daily_loss_usd": round(s.daily_loss_usd, 2),
        "daily_loss_percent": round(s.daily_loss_percent, 2),
        "weekly_loss_usd": round(s.weekly_loss_usd, 2),
        "protection_level": s.protection_level.value,
        "halt_reason": s.halt_reason,
    }


@router.post("/equity/resume")
async def manual_resume():
    """Admin: manually clear halt state."""
    engine = get_equity_protection()
    engine.manual_resume()
    return {"resumed": True, "level": engine.state.protection_level.value}


@router.post("/correlation/check")
async def check_correlation(req: CorrelationCheckRequest):
    """Get correlation coefficient between two symbols."""
    cf = get_correlation_filter()
    corr = cf.get_correlation(req.symbol_a, req.symbol_b)
    return {
        "symbol_a": req.symbol_a,
        "symbol_b": req.symbol_b,
        "correlation": corr,
        "interpretation": (
            "HIGHLY_CORRELATED" if corr and abs(corr) >= 0.8 else
            "MODERATELY_CORRELATED" if corr and abs(corr) >= 0.5 else
            "WEAKLY_CORRELATED" if corr else "UNKNOWN"
        ),
    }


@router.post("/lot-sizing/config")
async def update_lot_sizing_config(req: LotSizingConfigUpdate):
    """Update lot sizing configuration from dashboard."""
    sizer = get_lot_sizer()
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if "method" in updates:
        try:
            updates["method"] = LotSizingMethod(updates["method"])
        except ValueError:
            raise HTTPException(400, f"Invalid method: {updates['method']}")
    sizer.update_config(**updates)
    cfg = sizer.config
    return {
        "updated": True,
        "method": cfg.method.value,
        "risk_percent": cfg.risk_percent,
        "max_risk_percent": cfg.max_risk_percent,
        "atr_multiplier": cfg.atr_multiplier,
        "min_lot": cfg.min_lot,
        "max_lot": cfg.max_lot,
    }


@router.get("/status")
async def get_risk_status():
    """Overall risk system status."""
    equity  = get_equity_protection()
    sizer   = get_lot_sizer()
    s = equity.state
    return {
        "system": "Galaxy Vast Risk Management v2",
        "protection_level": s.protection_level.value,
        "can_trade": s.protection_level.value in ("SAFE", "WARNING"),
        "drawdown_percent": round(s.current_drawdown_percent, 2),
        "consecutive_losses": s.consecutive_losses,
        "daily_loss_percent": round(s.daily_loss_percent, 2),
        "lot_sizing_method": sizer.config.method.value,
        "risk_per_trade_percent": sizer.config.risk_percent,
    }


@router.post("/reset/daily")
async def reset_daily():
    """Reset daily counters — call at midnight."""
    get_risk_orchestrator().reset_daily()
    return {"reset": "daily", "timestamp": __import__("datetime").datetime.utcnow().isoformat()}

@router.post("/reset/weekly")
async def reset_weekly():
    """Reset weekly counters."""
    get_risk_orchestrator().reset_weekly()
    return {"reset": "weekly"}

@router.post("/reset/monthly")
async def reset_monthly():
    """Reset monthly counters."""
    get_risk_orchestrator().reset_monthly()
    return {"reset": "monthly"}
