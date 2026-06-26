"""audit_routes_v21.py — Phase 21 Admin Audit Routes"""
from backend.core.audit_log_v21 import audit_logger as _default_logger, AuditEvent, EVENT_SEVERITY, REQUIRES_REASON, Severity, AuditLogger
from typing import Optional, Dict, Any, List


class AuditRouter:
    """Thin router adapter — call methods directly in tests."""

    def __init__(self, logger: Optional[AuditLogger] = None) -> None:
        self._logger = logger if logger is not None else _default_logger

    def list_audit(self, *, user_id=None, tenant_id=None, event=None,
                   severity=None, since_ts=None, until_ts=None,
                   limit=100) -> Dict[str, Any]:
        records = self._logger.query(
            user_id=user_id, tenant_id=tenant_id, event=event,
            severity=severity, since_ts=since_ts, until_ts=until_ts,
            limit=limit
        )
        return {"count": len(records), "records": [r.to_dict() for r in records]}

    def summary(self) -> Dict[str, Any]:
        return self._logger.summary()

    def verify(self, actor_id: str = "admin") -> Dict[str, Any]:
        ok = self._logger.verify_chain()
        self._logger.admin_chain_verify(user_id=actor_id)
        return {"valid": ok, "message": "Chain integrity OK" if ok else "TAMPER DETECTED"}

    def tampered_seqs(self) -> Dict[str, Any]:
        broken = self._logger.detect_tampered()
        return {"tampered_count": len(broken), "tampered_seqs": broken}

    def export_jsonl(self, *, actor_id: str = "admin", tenant_id=None) -> str:
        self._logger.admin_audit_export(user_id=actor_id)
        return self._logger.export_jsonl(tenant_id=tenant_id)

    def export_csv(self, *, actor_id: str = "admin", tenant_id=None) -> str:
        self._logger.admin_audit_export(user_id=actor_id)
        return self._logger.export_csv()

    def list_events(self) -> Dict[str, Any]:
        events = []
        for e in AuditEvent:
            sev = EVENT_SEVERITY.get(e, Severity.INFO)
            events.append({"event": e.value, "severity": sev.value,
                           "requires_reason": e in REQUIRES_REASON})
        return {"count": len(events), "events": events}

    def user_trail(self, user_id: str, limit: int = 100) -> Dict[str, Any]:
        records = self._logger.query(user_id=user_id, limit=limit)
        return {"user_id": user_id, "count": len(records),
                "records": [r.to_dict() for r in records]}

    def test_event(self, user_id: str = "admin-test",
                   tenant_id: str = "default") -> Dict[str, Any]:
        rec = self._logger.auth_login_ok(user_id, tenant_id=tenant_id)
        return {"recorded": True, "seq": rec.seq, "event": rec.event,
                "chain_hash": rec.chain_hash[:16] + "..."}


try:
    from fastapi import APIRouter
    router = APIRouter(prefix="/admin/audit", tags=["audit"])
except ImportError:
    pass
