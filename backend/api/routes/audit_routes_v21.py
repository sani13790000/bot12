"""
backend/api/routes/audit_routes_v21.py — Phase 21
==================================================
Admin endpoints for forensic audit trail access.

Routes:
  GET  /admin/audit/              → query with filters
  GET  /admin/audit/summary       → chain summary (counts + last hash)
  GET  /admin/audit/verify        → full chain integrity check
  GET  /admin/audit/tamper        → list tampered seq numbers
  GET  /admin/audit/export.jsonl  → JSONL forensic export
  GET  /admin/audit/export.csv    → CSV forensic export
  GET  /admin/audit/events        → all 64 known event types + metadata
  GET  /admin/audit/user/{uid}    → per-user forensic trail
  POST /admin/audit/test          → write test event (dev/staging only)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.core.audit_log_v21 import (
    AuditEvent,
    AuditLogger,
    AuditRecord,
    EVENT_SEVERITY,
    REQUIRES_REASON,
    Severity,
    audit_logger as _global_logger,
)


class AuditRouter:
    """
    Thin router adapter — works with both FastAPI and plain Python tests.
    In FastAPI, wrap each method in an @router.get(...) decorator.
    In tests, call methods directly.
    """

    def __init__(self, logger: Optional[AuditLogger] = None) -> None:
        self._logger = logger if logger is not None else _global_logger

    def list_audit(
        self,
        *,
        user_id:   Optional[str] = None,
        tenant_id: Optional[str] = None,
        event:     Optional[str] = None,
        severity:  Optional[str] = None,
        since_ts:  Optional[float] = None,
        until_ts:  Optional[float] = None,
        limit:     int = 100,
    ) -> Dict[str, Any]:
        evt_enum = AuditEvent(event)  if event    else None
        sev_enum = Severity(severity) if severity else None
        records  = self._logger.query(
            user_id=user_id, tenant_id=tenant_id,
            event=evt_enum, severity=sev_enum,
            since_ts=since_ts, until_ts=until_ts,
            limit=limit,
        )
        return {"count": len(records), "records": [r.to_dict() for r in records]}

    def summary(self) -> Dict[str, Any]:
        return self._logger.summary()

    def verify(self) -> Dict[str, Any]:
        ok = self._logger.verify_chain()
        return {"valid": ok,
                "message": "Chain integrity OK" if ok else "TAMPER DETECTED"}

    def tampered_seqs(self) -> Dict[str, Any]:
        broken = self._logger.detect_tampered()
        return {"tampered_count": len(broken), "tampered_seqs": broken}

    def export_jsonl(self, *, tenant_id: Optional[str] = None) -> str:
        self._logger.admin_audit_export(
            user_id="admin",
            tenant_id=tenant_id or "all",
            detail={"format": "jsonl"},
        )
        return self._logger.export_jsonl(tenant_id=tenant_id)

    def export_csv(self, *, tenant_id: Optional[str] = None) -> str:
        self._logger.admin_audit_export(
            user_id="admin",
            tenant_id=tenant_id or "all",
            detail={"format": "csv"},
        )
        return self._logger.export_csv(tenant_id=tenant_id)

    def list_events(self) -> Dict[str, Any]:
        events = []
        for e in AuditEvent:
            sev = EVENT_SEVERITY.get(e, Severity.INFO)
            events.append({
                "event":           e.value,
                "severity":        sev.value,
                "requires_reason": e in REQUIRES_REASON,
            })
        return {"count": len(events), "events": events}

    def user_trail(self, user_id: str, limit: int = 100) -> Dict[str, Any]:
        records = self._logger.query(user_id=user_id, limit=limit)
        return {"user_id": user_id, "count": len(records),
                "records": [r.to_dict() for r in records]}

    def test_event(self, user_id: str = "admin-test",
                   tenant_id: str = "default") -> Dict[str, Any]:
        rec = self._logger.auth_login_ok(
            user_id=user_id, tenant_id=tenant_id,
            detail={"source": "audit_test_endpoint"})
        return {"recorded": True, "seq": rec.seq, "event": rec.event,
                "chain_hash": rec.chain_hash[:16] + "..."}
