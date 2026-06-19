"""\nbackend/api/routes/security_ai_extended.py\nPhase-4/5/6 endpoints: Threat Intel + Rules + Reports\n"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter(tags=["security-extended"])
_REPORTS_DIR = Path(os.getenv("SECURITY_REPORTS_DIR", "/reports/security"))


class RulesPatchRequest(BaseModel):
    patch: Dict[str, Any]


class GenerateReportRequest(BaseModel):
    period_hours: int = 24


async def _admin(_: Any = None) -> None:
    try:
        from backend.core.deps import require_admin
        await require_admin(_)
    except ImportError:
        pass


@router.get("/threat-intel/{ip}")
async def check_ip(ip: str) -> Dict[str, Any]:
    try:
        from backend.services.threat_intelligence_service import threat_intelligence_service
        r = await threat_intelligence_service.check_ip(ip)
        return {"ip": r.ip, "threat_level": r.threat_level.value, "confidence_score": r.confidence_score,
                "risk_score": r.risk_score, "is_tor": r.is_tor, "is_vpn": r.is_vpn,
                "is_datacenter": r.is_datacenter, "country_code": r.country_code,
                "provider": r.provider, "cached": r.cached, "error": r.error}
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Threat intelligence unavailable")


@router.get("/threat-intel-stats")
async def threat_stats() -> Dict[str, Any]:
    from backend.services.threat_intelligence_service import threat_intelligence_service
    return threat_intelligence_service.stats()


@router.get("/rules")
async def get_rules() -> Dict[str, Any]:
    from backend.core.security_rules_loader import security_rules
    return await security_rules.get()


@router.post("/rules")
async def update_rules(body: RulesPatchRequest, _: None = Depends(_admin)) -> Dict[str, Any]:
    from backend.core.security_rules_loader import security_rules
    await security_rules.update(body.patch)
    return {"status": "updated", "patch_keys": list(body.patch.keys())}


@router.get("/rules/anomaly")
async def anomaly_rules() -> Dict[str, Any]:
    from backend.core.security_rules_loader import security_rules
    r = await security_rules.anomaly()
    return {"contamination": r.contamination, "n_estimators": r.n_estimators,
            "score_medium": r.medium, "score_high": r.high, "score_critical": r.critical,
            "retrain_interval_seconds": r.retrain_interval_seconds}


@router.post("/reports/generate")
async def gen_report(body: GenerateReportRequest, _: None = Depends(_admin)) -> Dict[str, Any]:
    from backend.security_reporting.report_scheduler import report_scheduler
    rid = await report_scheduler.trigger(period_hours=body.period_hours)
    return {"status": "generated", "report_id": rid, "period_hours": body.period_hours}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, _: None = Depends(_admin)) -> Any:
    safe = "".join(c for c in report_id if c.isalnum() or c == "-")[:64]
    p = _REPORTS_DIR / f"{safe}.json"
    if not p.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(str(p), media_type="application/json")


@router.get("/reports/{report_id}/html")
async def get_report_html(report_id: str, _: None = Depends(_admin)) -> HTMLResponse:
    safe = "".join(c for c in report_id if c.isalnum() or c == "-")[:64]
    p = _REPORTS_DIR / f"{safe}.html"
    if not p.exists():
        raise HTTPException(404, "Report not found")
    return HTMLResponse(p.read_text(encoding="utf-8"))


@router.get("/reports")
async def list_reports(limit: int = Query(20, ge=1, le=100), _: None = Depends(_admin)) -> Dict[str, Any]:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(_REPORTS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:limit]
    return {"reports": [{"report_id": f.stem, "size_bytes": f.stat().st_size, "has_html": (f.parent / f"{f.stem}.html").exists(), "has_pdf": (f.parent / f"{f.stem}.pdf").exists()} for f in files], "total": len(files)}


@router.get("/scheduler/stats")
async def sched_stats() -> Dict[str, Any]:
    from backend.security_reporting.report_scheduler import report_scheduler
    return report_scheduler.stats()
