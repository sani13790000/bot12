"""
backend/agents/security_score_engine.py
Phase-14: Security Score Engine — 8-dimension composite 0-100 score.
"""
from __future__ import annotations
import asyncio, json, logging, time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)
_SCORE_INTERVAL_SECONDS: int = 300
_SCORE_HISTORY_LIMIT: int = 288
_ALERT_THRESHOLD_CRITICAL: float = 40.0
_ALERT_THRESHOLD_WARNING: float = 65.0

class ScoreStatus(str, Enum):
    CRITICAL = "critical"; WARNING = "warning"; FAIR = "fair"
    GOOD = "good"; EXCELLENT = "excellent"

@dataclass
class DimensionScore:
    name: str; score: float; weight: float; status: ScoreStatus
    details: List[str] = field(default_factory=list)
    raw_metrics: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SecurityReport:
    timestamp: datetime; overall_score: float; status: ScoreStatus
    dimensions: List[DimensionScore]; top_risks: List[str]
    recommendations: List[str]; trend: str; score_delta_1h: float
    alert_triggered: bool = False; alert_message: str = ""

def _score_to_status(s: float) -> ScoreStatus:
    if s < 40: return ScoreStatus.CRITICAL
    if s < 66: return ScoreStatus.WARNING
    if s < 80: return ScoreStatus.FAIR
    if s < 90: return ScoreStatus.GOOD
    return ScoreStatus.EXCELLENT

async def _run_query(db: Any, fn) -> Any:
    return await asyncio.get_running_loop().run_in_executor(None, fn)

class _AuthDimensionScorer:
    WEIGHT = 0.20
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; metrics: Dict[str, Any] = {}; s = 100.0
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            r = await _run_query(db, lambda: db.table("security_audit_logs").select("id", count="exact").eq("event_type", "login_failed").gte("created_at", since).execute())
            failed = r.count or 0; metrics["failed_logins_1h"] = failed
            if failed > 100: s -= 30; details.append(f"Critical: {failed} failed logins")
            elif failed > 20: s -= 15; details.append(f"Warning: {failed} failed logins")
            elif failed > 5: s -= 5; details.append(f"Notice: {failed} failed logins")
            else: details.append("Auth healthy")
        except Exception as exc:
            logger.debug("AuthScorer: %s", exc); s = 70.0; details.append("Auth metrics unavailable")
        return DimensionScore(name="Authentication Security", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details, raw_metrics=metrics)

class _AnomalyDimensionScorer:
    WEIGHT = 0.20
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; metrics: Dict[str, Any] = {}; s = 100.0
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            r = await _run_query(db, lambda: db.table("security_ai_analysis").select("risk_level,anomaly_score").eq("is_anomaly", True).gte("created_at", since).execute())
            rows = r.data or []; total = len(rows)
            critical = sum(1 for x in rows if x.get("risk_level") == "critical")
            high = sum(1 for x in rows if x.get("risk_level") == "high")
            metrics.update({"anomalies_1h": total, "critical": critical, "high": high})
            if critical > 0: s -= 40; details.append(f"CRITICAL: {critical} critical anomalies")
            if high > 0: s -= 20; details.append(f"HIGH: {high} anomalies")
            if total > 50: s -= 15; details.append(f"Warning: {total} anomalies")
            if not details: details.append("No anomalies detected")
        except Exception as exc:
            logger.debug("AnomalyScorer: %s", exc); s = 75.0; details.append("AI analysis unavailable")
        return DimensionScore(name="AI Anomaly Detection", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details, raw_metrics=metrics)

class _APISecurityDimensionScorer:
    WEIGHT = 0.15
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; metrics: Dict[str, Any] = {}; s = 100.0
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            r = await _run_query(db, lambda: db.table("api_requests").select("status_code").gte("created_at", since).execute())
            rows = r.data or []; total = max(len(rows), 1)
            err_5xx = sum(1 for x in rows if (x.get("status_code") or 0) >= 500)
            err_4xx = sum(1 for x in rows if 400 <= (x.get("status_code") or 0) < 500)
            rate_429 = sum(1 for x in rows if (x.get("status_code") or 0) == 429)
            metrics.update({"total": total, "4xx": err_4xx, "5xx": err_5xx, "429": rate_429})
            if err_5xx / total > 0.05: s -= 30; details.append(f"5xx rate {err_5xx/total*100:.1f}%")
            if err_4xx / total > 0.20: s -= 15; details.append(f"4xx rate {err_4xx/total*100:.1f}%")
            if rate_429 > 50: s -= 10; details.append(f"{rate_429} rate-limit hits")
            if not details: details.append("API error rates normal")
        except Exception as exc:
            logger.debug("APIScorer: %s", exc); s = 75.0; details.append("API metrics unavailable")
        return DimensionScore(name="API Security", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details, raw_metrics=metrics)

class _TradingSecurityDimensionScorer:
    WEIGHT = 0.15
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; s = 100.0
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            r = await _run_query(db, lambda: db.table("trades").select("volume,status").gte("created_at", since).execute())
            rows = r.data or []; total = max(len(rows), 1)
            rejected = sum(1 for x in rows if x.get("status") == "rejected")
            rr = rejected / total
            if rr > 0.3: s -= 25; details.append(f"{rr*100:.0f}% trade rejection")
            elif rr > 0.1: s -= 10; details.append(f"{rr*100:.0f}% trade rejection")
            else: details.append("Trading patterns normal")
        except Exception as exc:
            logger.debug("TradingScorer: %s", exc); s = 80.0; details.append("Trading metrics unavailable")
        return DimensionScore(name="Trading Security", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details)

class _SessionSecurityDimensionScorer:
    WEIGHT = 0.10
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; metrics: Dict[str, Any] = {}; s = 100.0
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            r = await _run_query(db, lambda: db.table("revoked_tokens").select("id", count="exact").gte("created_at", since).execute())
            revoked = r.count or 0; metrics["revoked_tokens_1h"] = revoked
            if revoked > 20: s -= 30; details.append(f"{revoked} tokens revoked")
            elif revoked > 5: s -= 15; details.append(f"{revoked} tokens revoked")
            else: details.append("Session security healthy")
        except Exception as exc:
            logger.debug("SessionScorer: %s", exc); s = 80.0
        return DimensionScore(name="Session Security", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details, raw_metrics=metrics)

class _InfrastructureDimensionScorer:
    WEIGHT = 0.10
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; s = 100.0; db_ok = False; redis_ok = False
        try:
            await _run_query(db, lambda: db.table("signals").select("id").limit(1).execute())
            db_ok = True; details.append("Database healthy")
        except Exception: s -= 40; details.append("Database unreachable")
        try:
            import redis.asyncio as aioredis
            from backend.core.config import settings
            r = aioredis.from_url(settings.REDIS_URL, socket_timeout=2)
            await r.ping(); await r.aclose(); redis_ok = True; details.append("Redis healthy")
        except Exception: s -= 20; details.append("Redis unreachable")
        return DimensionScore(name="Infrastructure", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details, raw_metrics={"db_ok": db_ok, "redis_ok": redis_ok})

class _DataIntegrityDimensionScorer:
    WEIGHT = 0.05
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; s = 100.0
        try:
            r = await _run_query(db, lambda: db.table("trades").select("id", count="exact").is_("symbol", "null").execute())
            n = r.count or 0
            if n > 0: s -= 20; details.append(f"{n} trades with null symbol")
            else: details.append("Data integrity OK")
        except Exception as exc:
            logger.debug("DataIntegrityScorer: %s", exc); s = 85.0
        return DimensionScore(name="Data Integrity", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details)

class _ComplianceDimensionScorer:
    WEIGHT = 0.05
    async def score(self, db: Any, window_minutes: int = 60) -> DimensionScore:
        details: List[str] = []; s = 100.0
        try:
            since = (datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).isoformat()
            r = await _run_query(db, lambda: db.table("security_audit_logs").select("id", count="exact").gte("created_at", since).execute())
            n = r.count or 0
            if n > 0: details.append(f"{n} audit events in 1h")
            else: s -= 20; details.append("No audit events in 1h")
        except Exception as exc:
            logger.debug("ComplianceScorer: %s", exc); s = 80.0
        return DimensionScore(name="Compliance and Audit", score=max(0.0, s), weight=self.WEIGHT, status=_score_to_status(s), details=details)


class SecurityScoreEngine:
    """Phase-14: Composite security score engine — 8 dimensions, 5-min refresh."""
    _SCORERS = [
        _AuthDimensionScorer(), _AnomalyDimensionScorer(), _APISecurityDimensionScorer(),
        _TradingSecurityDimensionScorer(), _SessionSecurityDimensionScorer(),
        _InfrastructureDimensionScorer(), _DataIntegrityDimensionScorer(), _ComplianceDimensionScorer(),
    ]

    def __init__(self) -> None:
        self._db_client: Any = None
        self._score_task: Optional[asyncio.Task] = None
        self._history: List[Tuple[datetime, float]] = []
        self._last_report: Optional[SecurityReport] = None
        self._compute_count: int = 0

    async def start(self) -> None:
        try:
            from backend.database.connection import get_db_client
            self._db_client = await get_db_client()
        except Exception as exc:
            logger.warning("SecurityScoreEngine: DB unavailable: %s", exc)
        try:
            await self.compute_score()
        except Exception as exc:
            logger.warning("SecurityScoreEngine: initial compute failed: %s", exc)
        self._score_task = asyncio.create_task(self._score_loop(), name="security_score_engine")
        logger.info("SecurityScoreEngine: started")

    async def stop(self) -> None:
        if self._score_task and not self._score_task.done():
            self._score_task.cancel()
            try: await self._score_task
            except asyncio.CancelledError: pass
        logger.info("SecurityScoreEngine: stopped")

    async def _score_loop(self) -> None:
        while True:
            await asyncio.sleep(_SCORE_INTERVAL_SECONDS)
            try: await self.compute_score()
            except Exception as exc: logger.error("SecurityScoreEngine: loop error: %s", exc)

    async def compute_score(self) -> SecurityReport:
        t0 = time.monotonic()
        tasks = [asyncio.create_task(sc.score(self._db_client)) for sc in self._SCORERS]
        dimensions: List[DimensionScore] = []
        for coro in asyncio.as_completed(tasks):
            try: dimensions.append(await coro)
            except Exception as exc: logger.error("scorer failed: %s", exc)
        total_w = sum(d.weight for d in dimensions)
        overall = round(max(0.0, min(100.0, sum(d.score * d.weight for d in dimensions) / max(total_w, 0.001))), 2)
        now = datetime.now(timezone.utc)
        self._history.append((now, overall))
        cutoff = now - timedelta(hours=24)
        self._history = [(ts, s) for ts, s in self._history if ts > cutoff][-_SCORE_HISTORY_LIMIT:]
        trend, delta = self._calc_trend()
        risks = [d for dim in dimensions for d in dim.details if any(kw in d.lower() for kw in ("critical", "high", "unreachable"))][:5]
        recs = self._recommendations(dimensions, overall)
        alert = overall < _ALERT_THRESHOLD_WARNING
        msg = f"CRITICAL score: {overall:.1f}/100" if overall < _ALERT_THRESHOLD_CRITICAL else (f"WARNING score: {overall:.1f}/100" if alert else "")
        report = SecurityReport(
            timestamp=now, overall_score=overall, status=_score_to_status(overall),
            dimensions=sorted(dimensions, key=lambda d: d.weight, reverse=True),
            top_risks=risks, recommendations=recs, trend=trend, score_delta_1h=delta,
            alert_triggered=alert, alert_message=msg,
        )
        self._last_report = report; self._compute_count += 1
        logger.info("SecurityScoreEngine: score=%.1f status=%s (%.0fms)", overall, report.status.value, (time.monotonic()-t0)*1000)
        asyncio.create_task(self._persist_score(report))
        if alert: asyncio.create_task(self._send_alert(report))
        return report

    def get_last_report(self) -> Optional[SecurityReport]: return self._last_report
    def get_history(self) -> List[Dict[str, Any]]:
        return [{"timestamp": ts.isoformat(), "score": s} for ts, s in self._history]

    def to_json(self, report: Optional[SecurityReport] = None) -> Dict[str, Any]:
        r = report or self._last_report
        if r is None: return {"error": "No report available"}
        return {
            "timestamp": r.timestamp.isoformat(), "overall_score": r.overall_score,
            "status": r.status.value, "trend": r.trend, "score_delta_1h": r.score_delta_1h,
            "alert_triggered": r.alert_triggered, "alert_message": r.alert_message,
            "top_risks": r.top_risks, "recommendations": r.recommendations,
            "dimensions": [{"name": d.name, "score": d.score, "weight": d.weight,
                            "status": d.status.value, "details": d.details} for d in r.dimensions],
        }

    def to_html_report(self, report: Optional[SecurityReport] = None) -> str:
        r = report or self._last_report
        if r is None: return "<h1>No report available</h1>"
        colors = {"critical": "#dc2626", "warning": "#d97706", "fair": "#ca8a04", "good": "#16a34a", "excellent": "#0284c7"}
        c = colors.get(r.status.value, "#6b7280")
        rows = ""
        for d in r.dimensions:
            dc = colors.get(d.status.value, "#6b7280")
            det = "<br>".join(d.details) if d.details else "-"
            rows += f"<tr><td>{d.name}</td><td style='color:{dc}'>{d.score:.1f}</td><td>{d.status.value.upper()}</td><td>{det}</td></tr>"
        risks = "".join(f"<p style='color:#dc2626'>{risk}</p>" for risk in r.top_risks) or "<p>No critical risks</p>"
        recs  = "".join(f"<p>* {rec}</p>" for rec in r.recommendations)
        alert_html = f"<p style='color:#dc2626;font-weight:600'>ALERT: {r.alert_message}</p>" if r.alert_triggered else ""
        return ("<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
                f"<title>Security Report {r.timestamp.strftime('%Y-%m-%d %H:%M')} UTC</title>"
                "<style>body{font-family:system-ui,sans-serif;margin:2rem;background:#f9fafb}"
                f".score{{font-size:4rem;font-weight:700;color:{c}}}"
                "table{width:100%;border-collapse:collapse;margin-top:1rem}"
                "th,td{padding:.75rem 1rem;border:1px solid #e5e7eb;text-align:left}"
                "th{background:#f3f4f6}</style></head><body>"
                "<h1>GalaxyVast Security Report</h1>"
                f"<p>Generated: {r.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC</p>"
                f"<p class='score'>{r.overall_score:.1f}<span style='font-size:1.5rem'>/100</span></p>"
                f"<p>Status: {r.status.value.upper()} | Trend: {r.trend} ({r.score_delta_1h:+.1f} vs 1h ago)</p>"
                + alert_html +
                "<h2>Dimension Breakdown</h2><table><thead><tr>"
                "<th>Dimension</th><th>Score</th><th>Status</th><th>Details</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
                f"<h2>Top Risks</h2>{risks}<h2>Recommendations</h2>{recs}</body></html>")

    def _calc_trend(self) -> Tuple[str, float]:
        if len(self._history) < 2: return "stable", 0.0
        cur = self._history[-1][1]
        ago = datetime.now(timezone.utc) - timedelta(hours=1)
        past = [s for ts, s in self._history if ts <= ago]
        if not past: return "stable", 0.0
        delta = cur - past[-1]
        if delta > 2: return "improving", round(delta, 2)
        if delta < -2: return "degrading", round(delta, 2)
        return "stable", round(delta, 2)

    def _recommendations(self, dims: List[DimensionScore], overall: float) -> List[str]:
        recs: List[str] = []
        for d in dims:
            if d.score < 60:
                if "Authentication" in d.name: recs.append("Enable account lockout after 5 failed logins"); recs.append("Enforce MFA for admin users")
                elif "Anomaly" in d.name: recs.append("Investigate detected anomalies immediately")
                elif "API" in d.name: recs.append("Tighten rate limiting on high-traffic endpoints")
                elif "Infrastructure" in d.name: recs.append("Check DB and Redis connectivity immediately")
        if overall < 70: recs.append("Conduct immediate security incident review")
        return (recs or ["System security posture is healthy"])[:6]

    async def _persist_score(self, report: SecurityReport) -> None:
        if not self._db_client: return
        try:
            await asyncio.get_running_loop().run_in_executor(None,
                lambda: self._db_client.table("security_scores").insert({
                    "overall_score": report.overall_score, "status": report.status.value,
                    "trend": report.trend, "score_delta_1h": report.score_delta_1h,
                    "alert_triggered": report.alert_triggered,
                    "dimensions": json.dumps(self.to_json(report)["dimensions"]),
                    "top_risks": json.dumps(report.top_risks),
                    "created_at": report.timestamp.isoformat(),
                }).execute())
        except Exception as exc: logger.debug("SecurityScoreEngine: persist failed: %s", exc)

    async def _send_alert(self, report: SecurityReport) -> None:
        try:
            from backend.observability.alert_manager import alert_manager
            await alert_manager.send_alert(
                level="critical" if report.overall_score < _ALERT_THRESHOLD_CRITICAL else "warning",
                title="Security Score Alert", message=report.alert_message,
                metadata={"score": report.overall_score, "status": report.status.value},
            )
        except Exception as exc: logger.debug("SecurityScoreEngine: alert failed: %s", exc)


_engine_instance: Optional[SecurityScoreEngine] = None
_engine_lock = asyncio.Lock()

async def get_security_score_engine() -> SecurityScoreEngine:
    global _engine_instance
    if _engine_instance is not None: return _engine_instance
    async with _engine_lock:
        if _engine_instance is None:
            _engine_instance = SecurityScoreEngine()
            await _engine_instance.start()
    return _engine_instance
