"""
Galaxy Vast AI Trading Platform
Analytics API Routes — 12 production endpoints
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.analytics import AnalyticsService, TradeRecord, ReportGenerator

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

# ── Singleton service (injected via dependency) ──────────────────────────────
_service: Optional[AnalyticsService] = None
_reporter = ReportGenerator()


def get_analytics_service() -> AnalyticsService:
    global _service
    if _service is None:
        _service = AnalyticsService(db_pool=None)   # pool injected at startup
    return _service


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class TradeRecordIn(BaseModel):
    ticket:           int
    symbol:           str
    direction:        str              = Field(..., pattern="^(BUY|SELL)$")
    entry_price:      float
    exit_price:       float
    stop_loss:        float            = 0.0
    lot_size:         float            = 0.01
    profit_loss:      float
    pips:             float            = 0.0
    risk_amount:      float            = 0.0
    reward_amount:    float            = 0.0
    confidence_score: float            = Field(0.0, ge=0, le=100)
    session:          str              = "UNKNOWN"
    strategy_tags:    List[str]        = []
    open_time:        datetime
    close_time:       datetime


class AnalyticsQueryParams(BaseModel):
    symbol:          Optional[str]   = None
    period:          str             = "MONTH"
    initial_balance: float           = 10_000.0
    risk_free_rate:  float           = 0.05


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    symbol:  Optional[str] = Query(None, description="Filter by symbol (e.g. XAUUSD)"),
    period:  str           = Query("MONTH", description="ALL | TODAY | WEEK | MONTH | YEAR"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    """
    Lightweight analytics summary — no equity curve.
    Used by dashboard cards.
    """
    summary = await svc.get_summary(symbol=symbol, period=period)
    return {"success": True, "data": summary, "symbol": symbol or "ALL", "period": period}


@router.get("/full")
async def get_full_analytics(
    symbol:          Optional[str] = Query(None),
    period:          str           = Query("MONTH"),
    initial_balance: float         = Query(10_000.0),
    risk_free_rate:  float         = Query(0.05),
    svc:             AnalyticsService = Depends(get_analytics_service),
):
    """
    Full analytics with equity curve, drawdown curve, breakdowns.
    """
    result = await svc.get_analytics(
        symbol=symbol,
        period=period,
        initial_balance=initial_balance,
        risk_free_rate=risk_free_rate,
    )
    return {"success": True, "data": result.to_dict()}


@router.get("/metrics")
async def get_key_metrics(
    symbol:  Optional[str] = Query(None),
    period:  str           = Query("MONTH"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    """
    Only the 7 core quant metrics.
    Fast endpoint for dashboard widgets.
    """
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {
        "success": True,
        "symbol":  symbol or "ALL",
        "period":  period,
        "metrics": {
            "sharpe_ratio":     round(result.sharpe_ratio,  4),
            "sortino_ratio":    round(result.sortino_ratio, 4),
            "calmar_ratio":     round(result.calmar_ratio,  4),
            "profit_factor":    round(result.profit_factor, 4),
            "recovery_factor":  round(result.recovery_factor, 4)
                                if result.recovery_factor != float("inf") else 9999,
            "expectancy_r":     round(result.expectancy_r,  4),
            "max_drawdown_pct": round(result.max_drawdown_pct * 100, 4),
            "win_rate_pct":     round(result.win_rate * 100, 2),
            "net_profit":       round(result.net_profit, 2),
            "cagr_pct":         round(result.cagr * 100, 2),
        },
    }


@router.get("/equity-curve")
async def get_equity_curve(
    symbol:          Optional[str] = Query(None),
    period:          str           = Query("ALL"),
    initial_balance: float         = Query(10_000.0),
    svc:             AnalyticsService = Depends(get_analytics_service),
):
    """Equity curve data points for charting."""
    curve = await svc.get_equity_curve(
        symbol=symbol, period=period, initial_balance=initial_balance
    )
    return {"success": True, "count": len(curve), "curve": curve}


@router.get("/drawdown")
async def get_drawdown_curve(
    symbol:  Optional[str] = Query(None),
    period:  str           = Query("ALL"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    """Drawdown curve for risk visualization."""
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {
        "success":              True,
        "max_drawdown_pct":     round(result.max_drawdown_pct * 100, 4),
        "max_drawdown_amount":  round(result.max_drawdown_amount, 2),
        "avg_drawdown_pct":     round(result.avg_drawdown_pct * 100, 4),
        "curve":                result.drawdown_curve,
    }


@router.get("/compare")
async def compare_periods(
    symbol:  str                    = Query("XAUUSD"),
    periods: Optional[str]          = Query("WEEK,MONTH,YEAR"),
    svc:     AnalyticsService       = Depends(get_analytics_service),
):
    """Compare metrics across multiple time periods."""
    period_list = [p.strip() for p in (periods or "WEEK,MONTH,YEAR").split(",")]
    comparison  = await svc.get_metrics_comparison(symbol=symbol, periods=period_list)
    return {"success": True, "symbol": symbol, "comparison": comparison}


@router.get("/breakdown/symbol")
async def breakdown_by_symbol(
    period: str = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    """Per-symbol performance breakdown."""
    result = await svc.get_analytics(period=period)
    return {"success": True, "period": period, "by_symbol": result.by_symbol}


@router.get("/breakdown/session")
async def breakdown_by_session(
    symbol: Optional[str] = Query(None),
    period: str           = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    """Per-session performance breakdown (LONDON / NY / ASIAN)."""
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {"success": True, "period": period, "by_session": result.by_session}


@router.get("/report/json")
async def report_json(
    symbol:  Optional[str] = Query(None),
    period:  str           = Query("MONTH"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    """Full JSON analytics report — Galaxy Vast branded."""
    result    = await svc.get_analytics(symbol=symbol, period=period)
    reporter  = ReportGenerator()
    json_str  = reporter.to_json(result)
    return Response(content=json_str, media_type="application/json")


@router.get("/report/html")
async def report_html(
    symbol:  Optional[str] = Query(None),
    period:  str           = Query("MONTH"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    """Professional HTML analytics report — Galaxy Vast branded."""
    result   = await svc.get_analytics(symbol=symbol, period=period)
    reporter = ReportGenerator()
    html     = reporter.to_html(result, symbol=symbol or "ALL")
    return Response(content=html, media_type="text/html")


@router.post("/trades")
async def record_trade(
    trade: TradeRecordIn,
    svc:   AnalyticsService = Depends(get_analytics_service),
):
    """
    Record a closed trade into analytics_trades table.
    Call from MT5 EA after every trade close.
    """
    if not svc._pool:
        raise HTTPException(503, "Database not connected")
    try:
        import json as _json
        async with svc._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO analytics_trades (
                    ticket, symbol, direction, entry_price, exit_price,
                    stop_loss, lot_size, profit_loss, pips,
                    risk_amount, reward_amount, confidence_score,
                    session, strategy_tags, open_time, close_time
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16
                )
                ON CONFLICT (ticket) DO UPDATE SET
                    exit_price   = EXCLUDED.exit_price,
                    profit_loss  = EXCLUDED.profit_loss,
                    close_time   = EXCLUDED.close_time
            """,
                trade.ticket, trade.symbol, trade.direction,
                trade.entry_price, trade.exit_price, trade.stop_loss,
                trade.lot_size, trade.profit_loss, trade.pips,
                trade.risk_amount, trade.reward_amount, trade.confidence_score,
                trade.session, _json.dumps(trade.strategy_tags),
                trade.open_time, trade.close_time,
            )
        await svc.invalidate_cache(symbol=trade.symbol)
        return {"success": True, "ticket": trade.ticket, "message": "Trade recorded"}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@router.delete("/cache")
async def invalidate_cache(
    symbol: Optional[str] = Query(None),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    """Force analytics cache invalidation."""
    await svc.invalidate_cache(symbol=symbol)
    return {"success": True, "message": "Cache invalidated", "symbol": symbol or "ALL"}
