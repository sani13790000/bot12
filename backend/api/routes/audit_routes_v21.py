"""
backend/api/routes/audit_routes_v21.py
Galaxy Vast AI Trading Platform — Audit API Routes (Phase 21)

Phase AB fix: restore from placeholder "AUDIT_CONTENT" (13 bytes) to full implementation.

BUG-AA3 fix: router = None guard on ImportError (not bare pass)

Endpoints (all require auth):
  GET  /admin/audit/chain       — retrieve tamper-evident audit chain
  POST /admin/audit/verify      — verify chain integrity
  GET  /admin/audit/export/csv  — export audit log as CSV
  GET  /admin/audit/stats       — audit statistics
  POST /admin/audit/log         — append manual audit event
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Depends, HTTPException, Query
    from pydantic import BaseModel, Field

    from backend.core.deps import get_current_user

    router = APIRouter(tags=["audit"])

    class ManualAuditRequest(BaseModel):
        event: str = Field(..., description="AuditEvent string")
        actor_id: str = Field(..., description="User ID performing the action")
        details: Dict[str, Any] = Field(default_factory=dict)
        severity: str = Field("INFO", pattern="^(INFO|WARNING|CRITICAL)$")

    @router.get("/chain")
    async def get_audit_chain(
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        _user: Any = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """Retrieve the tamper-evident audit chain records."""
        try:
            from backend.core.audit_log_v21 import get_audit_log

            log = get_audit_log()
            records = log.get_records(limit=limit, offset=offset)
            return {
                "status": "ok",
                "records": records,
                "count": len(records),
                "offset": offset,
                "limit": limit,
            }
        except Exception as exc:
            logger.exception("[audit] /chain error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/verify")
    async def verify_chain(_user: Any = Depends(get_current_user)) -> Dict[str, Any]:
        """Verify the integrity of the entire audit chain."""
        try:
            from backend.core.audit_log_v21 import get_audit_log

            log = get_audit_log()
            result = log.verify_chain()
            return {
                "status": "ok",
                "chain_valid": result.valid,
                "records_checked": result.records_checked,
                "first_broken": result.first_broken_index,
                "message": "Chain integrity verified" if result.valid else "Chain tampered!",
            }
        except Exception as exc:
            logger.exception("[audit] /verify error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/export/csv")
    async def export_audit_csv(
        limit: int = Query(10_000, ge=1, le=50_000),
        _user: Any = Depends(get_current_user),
    ) -> Any:
        """Export audit log as CSV download."""
        try:
            import io

            from fastapi.responses import StreamingResponse

            from backend.core.audit_log_v21 import get_audit_log

            log = get_audit_log()
            csv_bytes = log.export_csv(limit=limit)
            return StreamingResponse(
                io.BytesIO(csv_bytes),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
            )
        except Exception as exc:
            logger.exception("[audit] /export/csv error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/stats")
    async def audit_stats(_user: Any = Depends(get_current_user)) -> Dict[str, Any]:
        """Return audit log statistics."""
        try:
            from backend.core.audit_log_v21 import get_audit_log

            log = get_audit_log()
            return {"status": "ok", "data": log.stats()}
        except Exception as exc:
            logger.exception("[audit] /stats error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.post("/log")
    async def append_audit_event(
        req: ManualAuditRequest,
        _user: Any = Depends(get_current_user),
    ) -> Dict[str, Any]:
        """Manually append an audit event."""
        try:
            from backend.core.audit_log_v21 import get_audit_log

            log = get_audit_log()
            record = log.append(
                event=req.event,
                actor_id=req.actor_id,
                details=req.details,
                severity=req.severity,
            )
            return {"status": "ok", "record_id": record.record_id, "chain_hash": record.chain_hash}
        except Exception as exc:
            logger.exception("[audit] /log error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

except ImportError as _import_err:
    # BUG-AA3 fix: was bare pass — now router=None so callers can guard
    logger.warning("[audit_routes_v21] FastAPI unavailable — router disabled: %s", _import_err)
    router = None  # type: ignore[assignment]
