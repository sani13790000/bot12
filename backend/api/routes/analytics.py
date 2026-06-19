"""
backend/api/routes/analytics.py
Phase-8 (existing) + Phase-11 (security dashboard metrics) — complete merged file.

Endpoints added in Phase-11:
  GET /api/v1/analytics/security/metrics        → live dashboard metrics
  GET /api/v1/analytics/security/report         → generate + return report (was Phase-8)
  GET /api/v1/analytics/security/score/history  → score timeline
  GET /api/v1/analytics/security/events         → recent security events
  GET /api/v1/analytics/security/dashboard      → single payload for frontend

All previous endpoints are UNCHANGED.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from backend.analytics import AnalyticsService, TradeRecord, ReportGenerator

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])

_service: Optional[AnalyticsService] = None
_reporter = ReportGenerator()


def _get_score_engine():
    try:
        from backend.security_reporting.security_score_engine import security_score_engine
        return security_score_engine
    except Exception:
        return None


def _get_report_service():
    try:
        from backend.security_reporting.security_report_service import SecurityReportService
        return SecurityReportService()
    except Exception:
        return None


def _get_ai_agent():
    try:
        from backend.agents.security_ai_agent import security_ai_agent
        return security_ai_agent
    except Exception:
        return None


def get_analytics_service() -> AnalyticsService:
    global _service
    if _service is None:
        _service = AnalyticsService(db_pool=None)
    return _service


class TradeRecordIn(BaseModel):
    ticket:           int
    symbol:           str
    direction:        str       = Field(..., pattern="^(BUY|SELL)$")
    entry_price:      float
    exit_price:       float
    stop_loss:        float     = 0.0
    lot_size:         float     = 0.01
    profit_loss:      float
    pips:             float     = 0.0
    risk_amount:      float     = 0.0
    reward_amount:    float     = 0.0
    confidence_score: float     = Field(0.0, ge=0, le=100)
    session:          str       = "UNKNOWN"
    strategy_tags:    List[str] = []
    open_time:        datetime
    close_time:       datetime


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


class SecurityMetricsResponse(BaseModel):
    security_score:     float
    score_level:        str
    score_trend:        str
    anomaly_rate:       float
    blocked_ips:        int
    active_threats:     int
    failed_logins_1h:   int
    suspicious_trades:  int
    model_accuracy:     float
    last_retrain:       Optional[str]
    circuit_breaker:    bool
    dimensions:         List[Dict[str, Any]] = []
    top_risks:          List[str]     = []
    generated_at:       str           = ""


# ── Existing endpoints (UNCHANGED) ──────────────────────────────────────────

@router.get("/summary")
async def get_summary(
    symbol: Optional[str]    = Query(None),
    period: str              = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
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
    symbol: Optional[str]    = Query(None),
    period: str              = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
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
            "expectancy_r":     round(result.expectancy_r, 4),
            "max_drawdown_pct": round(result.max_drawdown_pct * 100, 4),
            "win_rate_pct":     round(result.win_rate * 100, 2),
            "net_profit":       round(result.net_profit, 2),
            "cagr_pct":         round(result.cagr * 100, 2),
        },
    }


@router.get("/equity-curve")
async def get_equity_curve(
    symbol:          Optional[str]    = Query(None),
    period:          str              = Query("ALL"),
    initial_balance: float            = Query(10_000.0),
    svc:             AnalyticsService = Depends(get_analytics_service),
):
    curve = await svc.get_equity_curve(
        symbol=symbol, period=period, initial_balance=initial_balance
    )
    return {"success": True, "count": len(curve), "curve": curve}


@router.get("/drawdown")
async def get_drawdown_curve(
    symbol: Optional[str]    = Query(None),
    period: str              = Query("ALL"),
    svc:    AnalyticsService = Depends(get_analytics_service),
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
    symbol:  str            = Query("XAUUSD"),
    periods: Optional[str] = Query("WEEK,MONTH,YEAR"),
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
    period: str              = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    result = await svc.get_analytics(period=period)
    return {"success": True, "period": period, "by_session": result.by_session}


@router.get("/breakdown/weekday")
async def breakdown_by_weekday(
    period: str              = Query("MONTH"),
    svc:    AnalyticsService = Depends(get_analytics_service),
):
    result = await svc.get_analytics(period=period)
    return {"success": True, "period": period, "by_weekday": result.by_weekday}


@router.post("/trades/add")
async def add_trade(
    trade: TradeRecordIn,
    svc:   AnalyticsService = Depends(get_analytics_service),
):
    record = TradeRecord(**trade.model_dump())
    await svc.add_trade(record)
    return {"success": True, "message": "Trade added"}


@router.get("/performance")
async def get_performance(
    symbol:  Optional[str] = Query(None),
    period:  str           = Query("MONTH"),
    svc:     AnalyticsService = Depends(get_analytics_service),
):
    result = await svc.get_analytics(symbol=symbol, period=period)
    return {
        "success": True,
        "data": {
            "total_trades":       result.total_trades,
            "win_rate":           round(result.win_rate, 4),
            "profit_factor":      round(result.profit_factor, 4),
            "net_profit":         round(result.net_profit, 2),
            "sharpe_ratio":       round(result.sharpe_ratio, 4),
            "max_drawdown_pct":   round(result.max_drawdown_pct * 100, 2),
            "consecutive_wins":   result.consecutive_wins,
            "consecutive_losses": result.consecutive_losses,
        },
    }


# ── Phase-8: Security Report ──────────────────────────────────────────────────

@router.get("/security/report", response_model=SecurityReportMeta)
async def get_security_report(
    days:   int = Query(30, ge=1, le=365),
    format: str = Query("json", pattern="^(json|html|pdf)$"),
) -> SecurityReportMeta:
    svc = _get_report_service()
    if svc is None:
        raise HTTPException(status_code=503, detail="Security reporting service unavailable")
    try:
        report = await asyncio.wait_for(svc.generate_report(period_hours=days * 24), timeout=60.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Report generation timed out")
    except Exception as exc:
        log.error("Security report error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Report generation failed")

    json_path = html_path = pdf_path = None
    try:
        from backend.security_reporting.report_exporter import ReportExporter
        exporter  = ReportExporter()
        json_path = await exporter.export_json(report)
        if format in ("html", "pdf"):
            html_path = await exporter.export_html(report)
        if format == "pdf":
            pdf_path = await exporter.export_pdf(report)
    except Exception as exc:
        log.warning("Report export error: %s", exc)

    snap = _get_score_engine()
    snap = snap.current() if snap else None
    return SecurityReportMeta(
        report_id          = report.report_id,
        generated_at       = report.generated_at.isoformat(),
        period_hours       = report.period_hours,
        period_days        = round(report.period_hours / 24, 1),
        score              = snap.score if snap else report.security_score,
        score_trend        = snap.trend if snap else "stable",
        total_attacks      = report.attack_stats.get("total", 0),
        blocked_ips        = report.blocked_ips.get("total", 0),
        high_risk_accounts = len(report.high_risk_accounts),
        failed_logins      = report.total_failed_logins,
        json_path          = json_path,
        html_path          = html_path,
        pdf_path           = pdf_path,
    )


# ── Phase-11: Security Dashboard Metrics ─────────────────────────────────────

@router.get("/security/metrics", response_model=SecurityMetricsResponse)
async def get_security_metrics() -> SecurityMetricsResponse:
    """Live security metrics. Reads from in-memory cache — O(1), non-blocking."""
    now          = datetime.now(timezone.utc).isoformat()
    score_engine = _get_score_engine()
    snap         = score_engine.current() if score_engine else None

    security_score  = snap.score       if snap else 0.0
    score_level     = snap.level.value if snap else "unknown"
    score_trend     = snap.trend       if snap else "stable"
    dimensions      = snap.to_dict().get("dimensions", []) if snap else []
    top_risks       = snap.top_risks if snap else []
    circuit_breaker = getattr(score_engine, "_breaker_open", False) if score_engine else False

    agent       = _get_ai_agent()
    agent_stats = agent.stats() if agent else {}
    anomaly_rate      = float(agent_stats.get("anomaly_rate_1h", 0.0))
    active_threats    = int(agent_stats.get("active_threats", 0))
    model_accuracy    = float(agent_stats.get("model_accuracy", 0.0))
    last_retrain      = agent_stats.get("last_retrain")
    suspicious_trades = int(agent_stats.get("suspicious_trades", 0))

    blocked_ips      = 0
    failed_logins_1h = 0
    try:
        from backend.database.connection import get_db_client
        from datetime import timedelta
        db        = await get_db_client()
        one_h_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        res_b = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.table("security_blocked_ips")
                           .select("ip_address", count="exact")
                           .is_("expires_at", "null").execute()
            ), timeout=2.0,
        )
        blocked_ips = res_b.count or 0
        res_f = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                lambda: db.table("security_audit_logs")
                           .select("id", count="exact")
                           .eq("event_type", "login_failed")
                           .gte("created_at", one_h_ago).execute()
            ), timeout=2.0,
        )
        failed_logins_1h = res_f.count or 0
    except Exception as exc:
        log.debug("Security metrics DB error (non-fatal): %s", exc)

    return SecurityMetricsResponse(
        security_score    = round(security_score, 2),
        score_level       = score_level,
        score_trend       = score_trend,
        anomaly_rate      = round(anomaly_rate, 4),
        blocked_ips       = blocked_ips,
        active_threats    = active_threats,
        failed_logins_1h  = failed_logins_1h,
        suspicious_trades = suspicious_trades,
        model_accuracy    = round(model_accuracy, 4),
        last_retrain      = last_retrain,
        circuit_breaker   = circuit_breaker,
        dimensions        = dimensions,
        top_risks         = top_risks[:5],
        generated_at      = now,
    )


@router.get("/security/score/history")
async def get_score_history(
    points: int = Query(288, ge=1, le=288),
):
    engine = _get_score_engine()
    if engine is None:
        return {"success": True, "points": 0, "history": []}
    history = engine.history(points=points)
    return {
        "success":           True,
        "points":            len(history),
        "history":           history,
        "alert_threshold":   float(os.getenv("SECURITY_SCORE_ALERT",   "65")),
        "breaker_threshold": float(os.getenv("SECURITY_SCORE_BREAKER", "40")),
    }


@router.get("/security/events")
async def get_recent_security_events(
    limit:      int           = Query(20, ge=1, le=100),
    min_risk:   float         = Query(0.0, ge=0.0, le=1.0),
    event_type: Optional[str] = Query(None),
) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    try:
        from backend.database.connection import get_db_client
        db    = await get_db_client()
        query = (
            db.table("security_ai_analysis")
              .select("id,event_type,risk_score,user_id,ip_address,metadata,created_at")
              .gte("risk_score", min_risk)
              .order("created_at", desc=True)
              .limit(limit)
        )
        if event_type:
            query = query.eq("event_type", event_type)
        res = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(None, query.execute), timeout=3.0
        )
        for row in (res.data or []):
            meta = row.get("metadata") or {}
            events.append({
                "event_id":   str(row.get("id", "")),
                "event_type": row.get("event_type", ""),
                "risk_score": round(float(row.get("risk_score", 0)), 4),
                "ip_address": row.get("ip_address"),
                "user_id":    row.get("user_id"),
                "summary":    str(meta.get("summary", row.get("event_type", "")))[:120],
                "created_at": row.get("created_at", ""),
            })
    except Exception as exc:
        log.debug("Security events DB error (non-fatal): %s", exc)
    return {"success": True, "count": len(events), "events": events,
            "filters": {"min_risk": min_risk, "event_type": event_type}}


@router.get("/security/dashboard")
async def get_security_dashboard(
    history_points: int = Query(48, ge=1, le=288),
    events_limit:   int = Query(10, ge=1, le=50),
) -> Dict[str, Any]:
    """Aggregated dashboard payload — all sub-calls concurrent."""
    metrics_r, history_r, events_r = await asyncio.gather(
        get_security_metrics(),
        get_score_history(points=history_points),
        get_recent_security_events(limit=events_limit),
        return_exceptions=True,
    )

    def _safe(r, fb):
        return fb if isinstance(r, Exception) else r

    fb_metrics = SecurityMetricsResponse(
        security_score=0.0, score_level="unknown", score_trend="stable",
        anomaly_rate=0.0, blocked_ips=0, active_threats=0,
        failed_logins_1h=0, suspicious_trades=0,
        model_accuracy=0.0, last_retrain=None, circuit_breaker=False,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    metrics = _safe(metrics_r, fb_metrics)
    return {
        "success":    True,
        "metrics":    metrics.model_dump() if hasattr(metrics, "model_dump") else metrics,
        "history":    _safe(history_r, {}).get("history", []),
        "events":     _safe(events_r,  {}).get("events",  []),
        "thresholds": {
            "alert":   float(os.getenv("SECURITY_SCORE_ALERT",   "65")),
            "breaker": float(os.getenv("SECURITY_SCORE_BREAKER", "40")),
        },
    }
