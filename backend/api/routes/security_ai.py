"""
backend/api/routes/security_ai.py
Phase-13 and Phase-14 REST endpoints

GET  /api/v1/security-ai/status
POST /api/v1/security-ai/analyze
POST /api/v1/security-ai/retrain
GET  /api/v1/security-ai/score
GET  /api/v1/security-ai/score/refresh
GET  /api/v1/security-ai/score/history
GET  /api/v1/security-ai/score/report (HTML)
GET  /api/v1/security-ai/anomalies
POST /api/v1/security-ai/block/{ip}
DELETE /api/v1/security-ai/block/{ip}
"""
from __future__ import annotations
import asyncio, ipaddress, logging, time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Security AI"])


class AnalyzeEventRequest(BaseModel):
    event_type: str = Field("api_request")
    ip_address: str = Field(..., max_length=45)
    user_id: Optional[str] = None
    endpoint: str = Field("", max_length=512)
    method: str = Field("GET")
    status_code: int = Field(200, ge=100, le=599)
    response_time_ms: float = Field(0.0, ge=0.0)
    payload_size: int = Field(0, ge=0)
    extra: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("ip_address")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        try: ipaddress.ip_address(v); return v
        except ValueError: raise ValueError(f"Invalid IP: {v}")

    @field_validator("event_type")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        allowed = {"api_request", "login_attempt", "trade_activity", "session_anomaly", "websocket"}
        if v not in allowed: raise ValueError(f"event_type must be one of {allowed}")
        return v


class BlockIPRequest(BaseModel):
    reason: str = Field("manual_block", max_length=255)
    duration_hours: int = Field(24, ge=1, le=720)


async def _get_agent():
    try:
        from backend.agents.security_ai_agent import get_security_agent
        return await get_security_agent()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Security AI agent unavailable: {exc}")

async def _get_engine():
    try:
        from backend.agents.security_score_engine import get_security_score_engine
        return await get_security_score_engine()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Security Score Engine unavailable: {exc}")


@router.get("/status", summary="Security AI Agent status")
async def get_agent_status(agent=Depends(_get_agent)) -> Dict[str, Any]:
    return {"status": "running", "stats": agent.stats(), "timestamp": datetime.now(timezone.utc).isoformat()}


@router.post("/analyze", summary="Analyze a security event")
async def analyze_event(req: AnalyzeEventRequest, agent=Depends(_get_agent)) -> Dict[str, Any]:
    try:
        from backend.agents.security_ai_agent import SecurityEvent, EventType
        event = SecurityEvent(
            event_type=EventType(req.event_type), ip_address=req.ip_address,
            user_id=req.user_id, endpoint=req.endpoint, method=req.method,
            status_code=req.status_code, response_time_ms=req.response_time_ms,
            payload_size=req.payload_size, extra=req.extra,
        )
        result = await agent.analyze_event(event)
        return {
            "is_anomaly": result.is_anomaly, "score": result.score,
            "risk_level": result.risk_level.value, "confidence": result.confidence,
            "explanation": result.explanation, "self_heal_action": result.self_heal_action,
        }
    except Exception as exc:
        logger.error("analyze_event error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/retrain", summary="Trigger manual model retraining")
async def retrain_model(agent=Depends(_get_agent)) -> Dict[str, Any]:
    success = await agent.retrain_model()
    return {"success": success, "message": "Model retrained" if success else "Not enough training data", "stats": agent.stats()}


@router.get("/score", summary="Current security score")
async def get_security_score(engine=Depends(_get_engine)) -> Dict[str, Any]:
    report = engine.get_last_report()
    if report is None: report = await engine.compute_score()
    return engine.to_json(report)


@router.get("/score/refresh", summary="Force recompute security score")
async def refresh_score(engine=Depends(_get_engine)) -> Dict[str, Any]:
    return engine.to_json(await engine.compute_score())


@router.get("/score/history", summary="Security score timeline (last 24h)")
async def get_score_history(engine=Depends(_get_engine)) -> Dict[str, Any]:
    history = engine.get_history()
    return {"history": history, "count": len(history)}


@router.get("/score/report", summary="HTML security report")
async def get_html_report(engine=Depends(_get_engine)) -> HTMLResponse:
    return HTMLResponse(content=engine.to_html_report(), status_code=200)


@router.get("/anomalies", summary="Recent anomaly detections")
async def list_anomalies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    risk_level: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    agent=Depends(_get_agent),
) -> Dict[str, Any]:
    try:
        from backend.database.connection import get_db_client
        db = await get_db_client()
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        query = (db.table("security_ai_analysis").select("*")
            .eq("is_anomaly", True).gte("created_at", since)
            .order("created_at", desc=True)
            .range((page - 1) * page_size, page * page_size - 1))
        if risk_level: query = query.eq("risk_level", risk_level)
        result = await asyncio.get_running_loop().run_in_executor(None, lambda: query.execute())
        return {"page": page, "page_size": page_size, "data": result.data or [], "agent_stats": agent.stats()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/block/{ip}", summary="Manually block IP")
async def block_ip(ip: str, req: BlockIPRequest) -> Dict[str, Any]:
    try: ipaddress.ip_address(ip)
    except ValueError: raise HTTPException(status_code=400, detail=f"Invalid IP: {ip}")
    try:
        from backend.agents.security_ai_agent import get_security_agent
        from backend.database.connection import get_db_client
        db = await get_db_client(); agent = await get_security_agent()
        unblock_at = datetime.now(timezone.utc) + timedelta(hours=req.duration_hours)
        agent._healer._blocked_ips[ip] = time.monotonic() + req.duration_hours * 3600
        await asyncio.get_running_loop().run_in_executor(None, lambda:
            db.table("security_blocked_ips").upsert({
                "ip_address": ip, "reason": req.reason, "blocked_by": "manual_admin",
                "unblock_at": unblock_at.isoformat(), "is_active": True,
            }).execute())
        return {"success": True, "ip": ip, "unblock_at": unblock_at.isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/block/{ip}", summary="Unblock IP")
async def unblock_ip(ip: str) -> Dict[str, Any]:
    try: ipaddress.ip_address(ip)
    except ValueError: raise HTTPException(status_code=400, detail=f"Invalid IP: {ip}")
    try:
        from backend.agents.security_ai_agent import get_security_agent
        from backend.database.connection import get_db_client
        db = await get_db_client(); agent = await get_security_agent()
        agent._healer._blocked_ips.pop(ip, None)
        await asyncio.get_running_loop().run_in_executor(None, lambda:
            db.table("security_blocked_ips").update({"is_active": False}).eq("ip_address", ip).execute())
        return {"success": True, "ip": ip, "status": "unblocked"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
