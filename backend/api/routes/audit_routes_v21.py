"""audit_routes_v21.py — Phase 21 Admin Audit Routes"""
from backend.core.audit_log_v21 import audit_logger as _default_logger, AuditEvent
from typing import Optional


class AuditRouter:
    """Minimal router wrapper for audit admin endpoints."""
    
    def __init__(self, logger=None):
        self._logger = logger or _default_logger

    @property
    def routes(self):
        return [
            _Route("/admin/audit"),
            _Route("/admin/audit/verify"),
            _Route("/admin/audit/export.jsonl"),
            _Route("/admin/audit/export.csv"),
            _Route("/admin/audit/events"),
            _Route("/admin/audit/user/{user_id}"),
            _Route("/admin/audit/test"),
        ]

    def list_audit(self, *, user_id=None, tenant_id=None, event=None,
                   severity=None, since_ts=None, limit=100):
        return self._logger.query(
            user_id=user_id, tenant_id=tenant_id, event=event,
            severity=severity, since_ts=since_ts, limit=limit
        )

    def summary(self):
        return self._logger.summary()

    def verify(self, actor_id: str = "admin"):
        ok = self._logger.verify_chain()
        self._logger.admin_chain_verify(user_id=actor_id)
        return {
            "valid":   ok,
            "message": "Chain integrity OK" if ok else "TAMPER DETECTED",
        }

    def tampered_seqs(self):
        broken = self._logger.detect_tampered()
        return {
            "tampered_count": len(broken),
            "tampered_seqs":  broken,
        }

    def export_jsonl(self, *, tenant_id=None, actor_id="admin"):
        self._logger.admin_audit_export(user_id=actor_id)
        return self._logger.export_jsonl(tenant_id=tenant_id)

    def export_csv(self, *, tenant_id=None):
        return self._logger.export_csv(tenant_id=tenant_id)

    def known_events(self):
        return [{"event": e.value, "name": e.name} for e in AuditEvent]

    def test_event(self, user_id: str = "test", message: str = "test"):
        self._logger.admin_chain_verify(user_id=user_id)
        return {"ok": True, "message": message}


class _Route:
    def __init__(self, path):
        self.path = path

    def __str__(self):
        return self.path


# FastAPI router (stub for import compatibility)
try:
    from fastapi import APIRouter
    router = APIRouter(prefix="/admin/audit", tags=["audit"])
except ImportError:
    class router:
        routes = [_Route(p) for p in [
            "/admin/audit", "/admin/audit/verify",
            "/admin/audit/export.jsonl", "/admin/audit/export.csv",
            "/admin/audit/events", "/admin/audit/user/{user_id}",
            "/admin/audit/test"
        ]]
