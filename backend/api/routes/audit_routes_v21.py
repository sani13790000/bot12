"""
backend/api/routes/audit_routes_v21.py — Phase 21
==================================================
Admin endpoints for forensic audit trail access.

Routes:
  GET  /admin/audit/              → query with filters
  GET  /admin/audit/summary       → chain summary (counts + last hash)
  GET  /admin/audit/verify        → verify chain integrity
  GET  /admin/audit/tamper        → detect tampered entries
  GET  /admin/audit/export.jsonl  → JSONL export
  GET  /admin/audit/export.csv    → CSV export
  GET  /admin/audit/events        → list all 64 event types
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.core.audit_log_v21 import (
    AuditEvent, AuditLogger, AuditChain, AuditRecord,
    REQUIRES_REASON, EVENT_SEVERITY, Severity,
    audit_logger,
)


# ── Simulated FastAPI-style router for test purposes ──────────────────────────

class AuditRouter:
    """Thin wrapper so tests can call route handlers directly."""

    def __init__(self, logger: Optional[AuditLogger] = None) -> None:
        self._al = logger or audit_logger

    # GET /admin/audit/
    def query_audit(self, *,
                    user_id: Optional[str]   = None,
                    tenant_id: Optional[str] = None,
                    event: Optional[str]     = None,
                    severity: Optional[str]  = None,
                    since_ts: Optional[float]= None,
                    until_ts: Optional[float]= None,
                    limit: int               = 200,
                    actor_id: Optional[str]  = None,  # who is requesting
                    ) -> Dict[str, Any]:
        # Record the admin accessing audit logs
        if actor_id:
            self._al.admin_export(actor_id=actor_id, since_ts=since_ts)
        records = self._al.query(
            user_id=user_id, tenant_id=tenant_id, event=event,
            severity=severity, since_ts=since_ts, until_ts=until_ts,
            limit=limit,
        )
        return {"records": records, "count": len(records)}

    # GET /admin/audit/summary
    def chain_summary(self, actor_id: str = "") -> Dict[str, Any]:
        summary = self._al.chain_summary()
        summary["verified"] = self._al.verify_chain()
        return summary

    # GET /admin/audit/verify
    def verify_chain(self, actor_id: str = "") -> Dict[str, Any]:
        if actor_id:
            self._al.chain._log  # access chain
            self._al.chain.record(
                AuditEvent.ADMIN_CHAIN_VERIFY, actor_id=actor_id
            )
        intact = self._al.verify_chain()
        tampered = self._al.detect_tamper() if not intact else []
        return {
            "intact":          intact,
            "tampered_seqs":   tampered,
            "tampered_count":  len(tampered),
        }

    # GET /admin/audit/tamper
    def detect_tamper(self, actor_id: str = "") -> Dict[str, Any]:
        broken = self._al.detect_tamper()
        return {
            "broken_seqs":  broken,
            "tampered":     len(broken) > 0,
            "count":        len(broken),
        }

    # GET /admin/audit/export.jsonl
    def export_jsonl(self, actor_id: str = "",
                     since_ts: Optional[float] = None) -> str:
        if actor_id:
            self._al.admin_export(actor_id=actor_id, since_ts=since_ts)
        return self._al.export_jsonl(since_ts=since_ts)

    # GET /admin/audit/export.csv
    def export_csv(self, actor_id: str = "") -> str:
        if actor_id:
            self._al.admin_export(actor_id=actor_id)
        return self._al.export_csv()

    # GET /admin/audit/events
    def list_events(self) -> Dict[str, Any]:
        events = []
        for ev in AuditEvent:
            events.append({
                "event":    ev.value,
                "severity": EVENT_SEVERITY.get(ev, Severity.INFO).value,
                "requires_reason": ev in REQUIRES_REASON,
            })
        return {"events": events, "count": len(events)}

    # GET /admin/audit/critical
    def get_critical(self, limit: int = 50) -> Dict[str, Any]:
        records = self._al.query(severity="CRITICAL", limit=limit)
        return {"records": records, "count": len(records)}


# Singleton router
audit_router = AuditRouter()
