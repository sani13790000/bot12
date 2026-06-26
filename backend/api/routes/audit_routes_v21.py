"""
backend/api/routes/audit_routes_v21.py — Phase 21
======================================================================
Admin endpoints for forensic audit trail access.

Endpoints:
  GET  /admin/audit                   → recent events + filters
  GET  /admin/audit/verify            → verify full chain
  GET  /admin/audit/export.jsonl      → raw JSONL export
  GET  /admin/audit/export.csv         → raw CSV export
  GET  /admin/audit/events             → list all known events
  GET  /admin/audit/user/{user_id}     → user-specific trail
  POST /admin/audit/test                → write test event (dev only)
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime, timezone
from typing import Any, Optional, List


# ----------------------------------------------------------------------------
#  Minimal inline stubs so this module imports without FastAPI or DB
# ----------------------------------------------------------------------------

try:
    from fastapi import APIRouter, HTTPException, Query, Depends
    from fastapi.responses import StreamingResponse
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    # minimal stub
    class APIRouter:  # type: ignore
        def __init__(self, **kw): self.routes = []
        def get(self, *a, **k): return lambda f: f
        def post(self, *a, **k): return lambda f: f
    class HTTPException(Exception):   # type: ignore
        def __init__(self, status_code, detail=None):
            self.status_code = status_code; self.detail = detail
    def Query(default=None, **kw): return default  # type: ignore
    def Depends(f=None): return None  # type: ignore
    class StreamingResponse:  # type: ignore
        def __init__(self, content, media_type=None, headers=None):
            self.content = content
            self.media_type = media_type
            self.headers = headers or {}


from backend.core.audit_log_v21 import (
    audit_logger, AuditEvent, Severity,
)


router = APIRouter(prefix="/admin/audit", tags=["Admin Audit"])


def _iso_ts(event_ts: float) -> str:
    """Convert epoch float to ISO-8601 string."""
    return datetime.fromtimestamp(event_ts, tz=timezone.utc).isoformat()


def _serialize_record(r):
    """Serialize an AuditRecord to a plain dict."""
    return {
        "seq": r.seq,
        "id": r.id,
        "event": r.event,
        "ts": _iso_ts(r.ts),
        "user_id": r.user_id,
        "tenant_id": r.tenant_id,
        "actor": r.actor,
        "severity": r.severity.value if hasattr(r.severity, "value") else str(r.severity),
        "reason": r.reason,
        "detail": r.detail,
        "chain_hash": r.chain_hash,
        "ip_address": r.ip_address,
        "device_id": r.device_id,
    }


@router.get("")
def list_audit_events(
    limit: int = 100,
    event: Optional[str] = None,
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    severity: Optional[str] = None,
    since_ts: Optional[float] = None,
):
    """Return recent audit records with optional filtering."""
    severity_enum = None
    if severity:
        try:
            severity_enum = Severity(severity.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    records = audit_logger.query(
        user_id=user_id,
        tenant_id=tenant_id,
        event=event,
        severity=severity_enum,
        since_ts=since_ts,
        limit=min(limit, 1000),
    )
    return {
        "total": len(records),
        "records": [serialize_record(r) for r in records],
    }


@router.get("/verify")
def verify_chain():
    """Verify the integrity of the entire audit chain."""
    result = audit_logger.verify_chain()
    return {
        "valid": result["valid"],
        "total_records": result["total_records"],
        "first_failed_seq": result.get("first_failed_seq"),
        "algorithm": "HMAC-SHA256",
        "verified_at": datetime.now(tz=timezone.utc).isoformat(),
    }


@router.get("/export.jsonl")
def export_jsonl():
    """Export full audit log as newline-delimited JSON."""
    data = audit_logger.export_jsonl()
    return StreamingResponse(
        content=iter([data.encode() if isinstance(data, str) else data]),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": "attachment; filename=audit.jsonl"},
    )


@router.get("/export.csv")
def export_csv():
    """Export full audit log as CSV."""
    data = audit_logger.export_csv()
    return StreamingResponse(
        content=iter([data.encode() if isinstance(data, str) else data]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit.csv"},
    )


@router.get("/events")
def list_known_events():
    """List all known audit event types with metadata."""
    from backend.core.audit_log_v21 import EVENT_META, REQUIRES_REASON
    events = []
    for ev, meta in EVENT_META.items():
        events.append({
            "event": ev,
            "severity": meta["severity"].value if hasattr(meta["severity"], "value") else str(meta["severity"]),
            "description": meta["description"],
            "requires_reason": ev in REQUIRES_REASON,
        })
    return {"total": len(events), "events": events}


@router.get("/user/{user_id}")
def user_audit_trail(user_id: str):
    """Return full audit trail for a specific user."""
    records = audit_logger.query(user_id=user_id, limit=1000)
    return {
        "user_id": user_id,
        "total": len(records),
        "records": [_serialize_record(r) for r in records],
    }


@router.post("/test")
def write_test_event(event: str = "system.error", reason: str = "Test event"):
    """Write a test audit event (for dev/staging only)."""
    record = audit_logger.record(
        event=event,
        user_id="test-system",
        actor="test-system",
        tenant_id="system",
        reason=reason,
        detail={"test": True},
    )
    return {"status": "ok", "seq": record.seq, "id": str(record.id)}
