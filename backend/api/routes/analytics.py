from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
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
    from backend.security_reporting.report_exporter import ReportExporter
    from backend.security_reporting.security_report_service import SecurityReportService

    _report_svc = SecurityReportService()
    _report_exp = ReportExporter()
    HAS_REPORTS = True
except ImportError:
    HAS_REPORTS = False

try:
    from backend.services.threat_intelligence_service import threat_intel_service  # noqa: F401

    HAS_THREAT = True
except ImportError:
    HAS_THREAT = False

try:
    from backend.database.connection import get_db_client

    HAS_DB = True
except ImportError:
    HAS_DB = False

try:
    from backend.core.deps import get_current_user, require_admin

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
    security_score: float
    score_level: str
    score_trend: str
    score_delta_1h: Optional[float] = None
    anomaly_rate: float
    anomalies_last_1h: int = 0
    anomalies_last_24h: int = 0
    critical_anomalies_24h: int = 0
    blocked_ips: int
    blocked_ips_24h: int = 0
    recent_security_events: List[Dict[str, Any]] = Field(default_factory=list)
    failed_logins_1h: int = 0
    suspicious_accounts: int = 0
    threat_intel_hits_24h: int = 0
    model_trained: bool = False
    model_samples: int = 0
    last_retrain: Optional[str] = None
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# BUG-AI2 fix: was @router.get("/analytics/security/metrics")
#   main.py registers with prefix="/analytics" so effective path was:
#   /analytics/analytics/security/metrics -> 404
@router.get(
    "/security/metrics",
    response_model=SecurityMetricsResponse,
    summary="Phase-11: Real-time security metrics for dashboard",
)
async def get_security_metrics() -> SecurityMetricsResponse:
    score = 75.0
    score_lvl = "moderate"
    trend = "stable"
    delta_1h = None
    model_ok = False
    model_n = 0
    last_rt: Optional[str] = None

    if HAS_SCORE:
        try:
            snap = security_score_engine.current_sync()
            if snap:
                score = snap.score
                score_lvl = snap.level.value if hasattr(snap.level, "value") else str(snap.level)
                trend = snap.trend
                delta_1h = snap.delta_1h
        except Exception as exc:
            log.warning("[analytics] security_score_engine unavailable: %s", exc)

    if HAS_AGENT:
        try:
            stats = security_ai_agent.get_stats()
            model_ok = stats.get("model_trained", False)
            model_n = stats.get("training_samples", 0)
            last_rt = stats.get("last_retrain")
        except Exception as exc:
            log.warning("[analytics] security_ai_agent.get_stats unavailable: %s", exc)

    anomalies_1h = 0
    anomalies_24h = 0
    critical_24h = 0
    blocked_now = 0
    blocked_24h = 0
    failed_1h = 0
    suspicious = 0
    threat_hits = 0
    recent_events: List[Dict[str, Any]] = []

    if HAS_DB:
        db = get_db_client()
        now = datetime.now(timezone.utc)
        h1 = (now - timedelta(hours=1)).isoformat()
        h24 = (now - timedelta(hours=24)).isoformat()

        async def _q(coro):
            try:
                return await coro
            except Exception as exc:
                log.warning("[analytics] DB query failed: %s", exc)
                return None

        results = await asyncio.gather(
            _q(db.table("security_ai_analysis").select("id").gte("detected_at", h1).execute()),
            _q(db.table("security_ai_analysis").select("id").gte("detected_at", h24).execute()),
            _q(
                db.table("security_ai_analysis")
                .select("id")
                .eq("severity", "critical")
                .gte("detected_at", h24)
                .execute()
            ),
            _q(db.table("security_blocked_ips").select("id").eq("is_active", True).execute()),
            _q(db.table("security_blocked_ips").select("id").gte("blocked_at", h24).execute()),
            _q(
                db.table("security_ai_analysis")
                .select("*")
                .order("detected_at", desc=True)
                .limit(10)
                .execute()
            ),
            return_exceptions=False,
        )

        if results[0]:
            anomalies_1h = len(results[0].data or [])
        if results[1]:
            anomalies_24h = len(results[1].data or [])
        if results[2]:
            critical_24h = len(results[2].data or [])
        if results[3]:
            blocked_now = len(results[3].data or [])
        if results[4]:
            blocked_24h = len(results[4].data or [])
        if results[5]:
            recent_events = results[5].data or []

    anomaly_rate = anomalies_1h / 60.0

    return SecurityMetricsResponse(
        security_score=score,
        score_level=score_lvl,
        score_trend=trend,
        score_delta_1h=delta_1h,
        anomaly_rate=round(anomaly_rate, 4),
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
