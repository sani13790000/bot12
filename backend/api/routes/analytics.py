from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

try:
    from backend.security_reporting.security_score_engine import security_score_engine
    HAS_SCORE = True
except ImportError:
    HAS_SCORE = False

try:
    from backend.agents.security_ai_agent import security_ai_agent
    HAS_AGENT = True
except ImportError:
    HAS_AGENT = False

try:
    from backend.security_reporting.security_report_service import SecurityReportService
    from backend.security_reporting.report_exporter import ReportExporter
    _report_svc = SecurityReportService()
    _report_exp = ReportExporter()
    HAS_REPORTS = True
except ImportError:
    HAS_REPORTS = False

try:
    from backend.services.threat_intelligence_service import threat_intel_service
    HAS_THREAT = True
except ImportError:
    HAS_THREAT = False

try:
    from backend.database.connection import get_db_client
    HAS_DB = True
except ImportError:
    HAS_DB = False

try:
    from backend.core.deps import require_admin, get_current_user
    HAS_AUTH = True
except ImportError:
    async def require_admin():
        return None
    async def get_current_user():
        return None
    HAS_AUTH = False

log = logging.getLogger(__name__)
router = APIRouter(tags=["analytics"])
_REPORTS_DIR = os.getenv("SECURITY_REPORTS_DIR", "/reports/security")


class SecurityMetricsResponse(BaseModel):
    security_score:          float
    score_level:             str
    score_trend:             str
    score_delta_1h:          Optional[float] = None
    anomaly_rate:            float
    anomalies_last_1h:       int   = 0
    anomalies_last_24h:      int   = 0
    critical_anomalies_24h:  int   = 0
    blocked_ips:             int
    blocked_ips_24h:         int   = 0
    recent_security_events:  List[Dict[str, Any]] = Field(default_factory=list)
    failed_logins_1h:        int   = 0
    suspicious_accounts:     int   = 0
    threat_intel_hits_24h:   int   = 0
    model_trained:           bool  = False
    model_samples:           int   = 0
    last_retrain:            Optional[str] = None
    generated_at:            str   = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@router.get("/analytics/security/metrics", response_model=SecurityMetricsResponse,
            summary="Phase-11: Real-time security metrics for dashboard")
async def get_security_metrics() -> SecurityMetricsResponse:
    score     = 75.0
    score_lvl = "moderate"
    trend     = "stable"
    delta_1h  = None
    model_ok  = False
    model_n   = 0
    last_rt: Optional[str] = None

    if HAS_SCORE:
        try:
            snap = security_score_engine.current_sync()
            if snap:
                score     = snap.score
                score_lvl = snap.level.value if hasattr(snap.level, "value") else str(snap.level)
                trend     = snap.trend
                delta_1h  = snap.delta_1h
        except Exception:
            pass

    if HAS_AGENT:
        try:
            stats    = security_ai_agent.get_stats()
            model_ok = stats.get("model_trained", False)
            model_n  = stats.get("training_samples", 0)
            last_rt  = stats.get("last_retrain")
        except Exception:
            pass

    anomalies_1h  = 0
    anomalies_24h = 0
    critical_24h  = 0
    blocked_now   = 0
    blocked_24h   = 0
    failed_1h     = 0
    suspicious    = 0
    threat_hits   = 0
    recent_events: List[Dict[str, Any]] = []

    if HAS_DB:
        db  = get_db_client()
        now = datetime.now(timezone.utc)
        h1  = (now - timedelta(hours=1)).isoformat()
        h24 = (now - timedelta(hours=24)).isoformat()

        async def _q(coro):
            try:
                return await asyncio.wait_for(coro, timeout=3.0)
            except Exception:
                return None

        results = await asyncio.gather(
            _q(db.table("security_ai_analysis").select("id", count="exact").gte("created_at", h1).execute()),
            _q(db.table("security_ai_analysis").select("id", count="exact").gte("created_at", h24).execute()),
            _q(db.table("security_ai_analysis").select("id", count="exact").gte("created_at", h24).eq("risk_level", "critical").execute()),
            _q(db.table("security_blocked_ips").select("id", count="exact").or_(f"expires_at.is.null,expires_at.gt.{now.isoformat()}").execute()),
            _q(db.table("security_blocked_ips").select("id", count="exact").gte("created_at", h24).execute()),
            _q(db.table("security_audit_logs").select("id", count="exact").eq("event_type", "login_failed").gte("created_at", h1).execute()),
            _q(db.table("users").select("id", count="exact").eq("is_flagged", True).execute()),
            _q(db.table("threat_intel_cache").select("id", count="exact").gte("queried_at", h24).gt("risk_score", 50).execute()),
            _q(db.table("security_ai_analysis").select("id,event_type,risk_level,ip_address,created_at").order("created_at", desc=True).limit(10).execute()),
            return_exceptions=False,
        )

        def _c(r) -> int:
            if r and hasattr(r, "count") and r.count is not None:
                return int(r.count)
            if r and hasattr(r, "data") and r.data:
                return len(r.data)
            return 0

        anomalies_1h  = _c(results[0])
        anomalies_24h = _c(results[1])
        critical_24h  = _c(results[2])
        blocked_now   = _c(results[3])
        blocked_24h   = _c(results[4])
        failed_1h     = _c(results[5])
        suspicious    = _c(results[6])
        threat_hits   = _c(results[7])
        if results[8] and results[8].data:
            recent_events = [
                {"id": e.get("id"), "event_type": e.get("event_type"),
                 "risk_level": e.get("risk_level"),
                 "ip_address": str(e.get("ip_address", ""))[:15],
                 "created_at": e.get("created_at")}
                for e in results[8].data
            ]

    total_req_1h = max(anomalies_1h * 10, 100)
    anomaly_rate = round((anomalies_1h / total_req_1h) * 1_000, 2)

    return SecurityMetricsResponse(
        security_score=round(score, 2),
        score_level=score_lvl,
        score_trend=trend,
        score_delta_1h=delta_1h,
        anomaly_rate=anomaly_rate,
        anomalies_last_1h=anomalies_1h,
        anomalies_last_24h=anomalies_24h,
        critical_anomalies_24h=critical_24h,
        blocked_ips=blocked_now,
        blocked_ips_24h=blocked_24h,
        recent_security_events=recent_events,
        failed_logins_1h=failed_1h,
        suspicious_accounts=suspicious,
        threat_intel_hits_24h=threat_hits,
        model_trained=model_ok,
        model_samples=model_n,
        last_retrain=last_rt,
    )


@router.get("/analytics/security/score/history",
            summary="Phase-11: 24h score history (288 points)")
async def get_score_history() -> JSONResponse:
    if not HAS_SCORE:
        return JSONResponse({"points": [], "interval_minutes": 5})
    hist = security_score_engine.history()
    return JSONResponse({
        "points": [{"score": round(s.score, 2), "level": s.level.value,
                    "timestamp": s.timestamp.isoformat()} for s in hist],
        "interval_minutes": 5, "total": len(hist),
    })


@router.get("/analytics/security/score/dimensions",
            summary="Phase-11: Per-dimension breakdown")
async def get_score_dimensions() -> JSONResponse:
    if not HAS_SCORE:
        return JSONResponse({"dimensions": []})
    snap = security_score_engine.current_sync()
    if snap is None:
        return JSONResponse({"dimensions": []})
    return JSONResponse({"score": round(snap.score, 2), "level": snap.level.value,
                         "dimensions": [d.to_dict() for d in snap.dimensions]})


@router.get("/analytics/security/anomalies",
            summary="Phase-11: Paginated anomaly feed")
async def get_anomaly_feed(
    limit:  int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    risk:   Optional[str] = Query(None),
    hours:  int = Query(24, ge=1, le=168),
) -> JSONResponse:
    if not HAS_DB:
        return JSONResponse({"items": [], "total": 0})
    db    = get_db_client()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    try:
        q = (db.table("security_ai_analysis")
               .select("id,event_type,risk_level,risk_score,ip_address,user_id,metadata,created_at",
                       count="exact")
               .gte("created_at", since)
               .order("created_at", desc=True)
               .range(offset, offset + limit - 1))
        if risk:
            q = q.eq("risk_level", risk)
        r = await asyncio.wait_for(q.execute(), timeout=3.0)
        return JSONResponse({"items": r.data or [], "total": r.count or 0,
                             "limit": limit, "offset": offset})
    except Exception as exc:
        log.warning("anomaly_feed error: %s", exc)
        return JSONResponse({"items": [], "total": 0})


@router.get("/analytics/security/blocked-ips",
            summary="Phase-11: Active blocked IPs")
async def get_blocked_ips(
    limit:  int  = Query(50, ge=1, le=200),
    active: bool = Query(True),
) -> JSONResponse:
    if not HAS_DB:
        return JSONResponse({"items": [], "total": 0})
    db  = get_db_client()
    now = datetime.now(timezone.utc).isoformat()
    try:
        q = (db.table("security_blocked_ips")
               .select("ip_address,reason,expires_at,auto_blocked,created_at", count="exact")
               .order("created_at", desc=True).limit(limit))
        if active:
            q = q.or_(f"expires_at.is.null,expires_at.gt.{now}")
        r = await asyncio.wait_for(q.execute(), timeout=3.0)
        return JSONResponse({"items": r.data or [], "total": r.count or 0})
    except Exception as exc:
        log.warning("blocked_ips error: %s", exc)
        return JSONResponse({"items": [], "total": 0})


@router.get("/analytics/security/threat-intel/{ip}",
            summary="Phase-11: Threat intel for IP")
async def get_threat_intel_for_ip(ip: str) -> JSONResponse:
    if not HAS_THREAT:
        return JSONResponse({"ip": ip, "available": False})
    try:
        report = await asyncio.wait_for(threat_intel_service.check_ip(ip), timeout=6.0)
        return JSONResponse(report.__dict__ if hasattr(report, "__dict__") else report)
    except Exception as exc:
        return JSONResponse({"ip": ip, "error": str(exc), "available": False})


class ReportMetaResponse(BaseModel):
    report_id:    str
    generated_at: str
    period_days:  float
    score:        Optional[float] = None
    score_trend:  Optional[str]   = None
    total_attacks: int            = 0
    blocked_ips:  int             = 0
    json_path:    Optional[str]   = None
    html_path:    Optional[str]   = None
    pdf_path:     Optional[str]   = None


@router.get("/analytics/security/report", response_model=ReportMetaResponse,
            summary="Phase-8: Generate security report")
async def generate_security_report(
    days: int = Query(30, ge=1, le=365),
) -> ReportMetaResponse:
    if not HAS_REPORTS:
        raise HTTPException(503, "Security reporting module not available.")
    try:
        report = await asyncio.wait_for(_report_svc.generate(days=days), timeout=30.0)
    except asyncio.TimeoutError:
        raise HTTPException(504, "Report generation timed out.")
    except Exception as exc:
        log.error("report generation failed: %s", exc)
        raise HTTPException(500, "Report generation failed.")

    json_path = html_path = pdf_path = None
    try:
        paths = await _report_exp.export_all(report, output_dir=_REPORTS_DIR)
        json_path = paths.get("json")
        html_path = paths.get("html")
        pdf_path  = paths.get("pdf")
    except Exception as exc:
        log.warning("export failed: %s", exc)

    return ReportMetaResponse(
        report_id=str(getattr(report, "report_id", uuid.uuid4())),
        generated_at=datetime.now(timezone.utc).isoformat(),
        period_days=float(days),
        score=getattr(report, "security_score", None),
        score_trend=getattr(report, "score_trend", None),
        total_attacks=(report.attack_stats.get("total", 0)
                       if hasattr(report, "attack_stats") and report.attack_stats else 0),
        blocked_ips=(report.blocked_ips.get("total_blocked", 0)
                     if hasattr(report, "blocked_ips") and report.blocked_ips else 0),
        json_path=json_path, html_path=html_path, pdf_path=pdf_path,
    )


@router.get("/analytics/security/report/{report_id}/html",
            summary="Download HTML report", response_class=HTMLResponse)
async def download_html_report(report_id: str) -> HTMLResponse:
    import re
    if not re.fullmatch(r"[0-9a-f\-]{36}", report_id):
        raise HTTPException(400, "Invalid report ID.")
    path = os.path.join(_REPORTS_DIR, f"{report_id}.html")
    if not os.path.isfile(path):
        raise HTTPException(404, "Report not found.")
    with open(path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/analytics/security/report/{report_id}/json",
            summary="Download JSON report")
async def download_json_report(report_id: str) -> JSONResponse:
    import json as _json, re
    if not re.fullmatch(r"[0-9a-f\-]{36}", report_id):
        raise HTTPException(400, "Invalid report ID.")
    path = os.path.join(_REPORTS_DIR, f"{report_id}.json")
    if not os.path.isfile(path):
        raise HTTPException(404, "Report not found.")
    with open(path, "r", encoding="utf-8") as f:
        return JSONResponse(_json.load(f))
