"""
backend/api/routes/analytics.py
Phase-8: Extended with GET /analytics/security/report
All existing endpoints preserved.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.analytics import AnalyticsService, TradeRecord, ReportGenerator

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

_service: Optional[AnalyticsService] = None
_reporter = ReportGenerator()


def get_analytics_service() -> AnalyticsService:
    global _service
    if _service is None:
        _service = AnalyticsService(db_pool=None)
    return _service


class TradeRecordIn(BaseModel):
    ticket:           int
    symbol:           str
    direction:        str           = Field(..., pattern="^(BUY|SELL)$")
    entry_price:      float
    exit_price:       float
    stop_loss:        float         = 0.0
    lot_size:         float         = 0.01
    profit_loss:      float
    pips:             float         = 0.0
    risk_amount:      float         = 0.0
    reward_amount:    float         = 0.0
    confidence_score: float         = Field(0.0, ge=0, le=100)
    session:          str           = "UNKNOWN"
    strategy_tags:    List[str]     = []
    open_time:        datetime
    close_time:       datetime


class AnalyticsQueryParams(BaseModel):
    symbol:          Optional[str] = None
    period:          str           = "MONTH"
    initial_balance: float         = 10_000.0
    risk_free_rate:  float         = 0.05


class SecurityReportMeta(BaseModel):
    report_id:          str
    generated_at:       str
    period_hours:       int
    period_days:        float
    score:              float
    score_trend:        str
    total_attacks:      int
    blocked_ips:        int
    high_risk_accounts: int
    failed_logins:      int
    json_path:          Optional[str]
    html_path:          Optional[str]
    pdf_path:           Optional[str]


@router.get("/summary")
async def get_summary(
    symbol: Optional[str]       = Query(None),
    period: str                 = Query("MONTH"),
    svc:    AnalyticsService    = Depends(get_analytics_service),
):
    summary = await svc.get_summary(symbol=symbol, period=period)
    return {"success": True, "data": summary, "symbol": symbol or "ALL", "period": period}


@router.get("/full")
async def get_full_analytics(
    symbol:          Optional[str]    = Query(None),
    period:          str              = Query("MONTH"),
    initial_balance: float            = Query(10_000.0),
    risk_free_rate:  float            = Query(0.05),
    svc:             AnalyticsService = Depends(get_analytics_service),
):
    result = await svc.get_analytics(
        symbol=symbol, period=period,
        initial_balance=initial_balance, risk_free_rate=risk_free_rate,
    )
    return {"success": True, "data": result.to_dict()}


@router.get("/metrics")
async def get_key_metrics(
    symbol: Optional[str]       = Query(None),
    period: str                 = Query("MONTH"),
    svc:    AnalyticsService    = Depends(get_analytics_service),
):
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {
        "success": True, "symbol": symbol or "ALL", "period": period,
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
    curve = await svc.get_equity_curve(symbol=symbol, period=period, initial_balance=initial_balance)
    return {"success": True, "count": len(curve), "curve": curve}


@router.get("/drawdown")
async def get_drawdown_curve(
    symbol: Optional[str]       = Query(None),
    period: str                 = Query("ALL"),
    svc:    AnalyticsService    = Depends(get_analytics_service),
):
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {
        "success":             True,
        "max_drawdown_pct":    round(result.max_drawdown_pct * 100, 4),
        "max_drawdown_amount": round(result.max_drawdown_amount, 2),
        "avg_drawdown_pct":    round(result.avg_drawdown_pct * 100, 4),
        "curve":               result.drawdown_curve,
    }


@router.get("/compare")
async def compare_periods(
    symbol:  str             = Query("XAUUSD"),
    periods: Optional[str]  = Query("WEEK,MONTH,YEAR"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    period_list = [p.strip() for p in (periods or "WEEK,MONTH,YEAR").split(",")]
    comparison  = await svc.get_metrics_comparison(symbol=symbol, periods=period_list)
    return {"success": True, "symbol": symbol, "comparison": comparison}


@router.get("/breakdown/symbol")
async def breakdown_by_symbol(
    period: str              = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    result = await svc.get_analytics(period=period)
    return {"success": True, "period": period, "by_symbol": result.by_symbol}


@router.get("/breakdown/session")
async def breakdown_by_session(
    symbol: Optional[str]   = Query(None),
    period: str             = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {"success": True, "period": period, "by_session": result.by_session}


@router.get("/report/json")
async def report_json(
    symbol: Optional[str]   = Query(None),
    period: str             = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    result   = await svc.get_analytics(symbol=symbol, period=period)
    reporter = ReportGenerator()
    json_str = reporter.to_json(result)
    return Response(content=json_str, media_type="application/json")


@router.get("/report/html")
async def report_html(
    symbol: Optional[str]   = Query(None),
    period: str             = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    result   = await svc.get_analytics(symbol=symbol, period=period)
    reporter = ReportGenerator()
    html     = reporter.to_html(result, symbol=symbol or "ALL")
    return Response(content=html, media_type="text/html")


@router.post("/trades")
async def record_trade(
    trade: TradeRecordIn,
    svc:   AnalyticsService = Depends(get_analytics_service),
):
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
                    exit_price  = EXCLUDED.exit_price,
                    profit_loss = EXCLUDED.profit_loss,
                    close_time  = EXCLUDED.close_time
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
    symbol: Optional[str]   = Query(None),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    await svc.invalidate_cache(symbol=symbol)
    return {"success": True, "message": "Cache invalidated", "symbol": symbol or "ALL"}


# Phase-8 Security Report Endpoint
@router.get(
    "/security/report",
    response_model=SecurityReportMeta,
    summary="Generate security report",
    tags=["Analytics", "Security"],
)
async def get_security_report(
    days: int = Query(default=30, ge=1, le=365, description="Number of days (default: 30)"),
) -> SecurityReportMeta:
    """
    Phase-8: Trigger security report and return metadata.
    days: 1-365 period to cover.
    """
    try:
        from backend.security_reporting.report_scheduler import report_scheduler
        run_record = await report_scheduler.trigger(
            period_hours=days * 24,
            label="api_manual",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {exc}")

    if run_record.get("error"):
        raise HTTPException(status_code=500, detail=f"Report error: {run_record['error']}")

    try:
        from backend.security_reporting.security_report_service import security_report_service
        report  = await security_report_service.generate_report(period_hours=days * 24)
        exports = run_record.get("exports", {})
        return SecurityReportMeta(
            report_id          = report.report_id,
            generated_at       = report.generated_at.isoformat()
                                 if hasattr(report.generated_at, "isoformat")
                                 else str(report.generated_at),
            period_hours       = report.period_hours,
            period_days        = round(report.period_hours / 24, 1),
            score              = round(report.security_score, 1),
            score_trend        = getattr(report, "score_trend", "stable"),
            total_attacks      = getattr(report.attack_stats, "total_detected", 0),
            blocked_ips        = getattr(report.blocked_ips, "currently_active", 0),
            high_risk_accounts = len(getattr(report, "high_risk_accounts", [])),
            failed_logins      = getattr(report, "total_failed_logins", 0),
            json_path          = exports.get("json"),
            html_path          = exports.get("html"),
            pdf_path           = exports.get("pdf"),
        )
    except Exception as exc:
        return SecurityReportMeta(
            report_id=run_record.get("report_id") or "unknown",
            generated_at=run_record.get("started_at") or "",
            period_hours=days * 24, period_days=float(days),
            score=0.0, score_trend="unknown",
            total_attacks=0, blocked_ips=0, high_risk_accounts=0, failed_logins=0,
            json_path=run_record.get("exports", {}).get("json"),
            html_path=run_record.get("exports", {}).get("html"),
            pdf_path=run_record.get("exports", {}).get("pdf"),
        )
