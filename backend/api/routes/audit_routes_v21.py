"""Phase 21 — Audit Admin Routes — 9 endpoints"""
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from backend.core.audit_log_v21 import (
    AuditChain, AuditEvent, AuditLogger, EVENT_META, REQUIRES_REASON, Severity,
)
_default_chain = AuditChain(secret="audit-chain-secret-v21")
audit_logger   = AuditLogger(chain=_default_chain)

def get_admin_audit_list(user_id=None,tenant_id=None,event=None,severity=None,
                         since_ts=None,until_ts=None,limit=100,actor_id="admin"):
    """GET /admin/audit/ — query + filter."""
    audit_logger.admin_audit_export(user_id=actor_id)
    records=audit_logger.query(user_id=user_id,tenant_id=tenant_id,event=event,
                               severity=severity,since_ts=since_ts,until_ts=until_ts,
                               limit=min(limit,1000))
    return {"records":[r.to_dict() for r in records],"count":len(records)}

def get_admin_audit_summary(actor_id="admin"):
    """GET /admin/audit/summary"""
    return audit_logger.summary()

def get_admin_audit_verify(actor_id="admin"):
    """GET /admin/audit/verify — chain integrity check."""
    audit_logger.admin_chain_verify(user_id=actor_id)
    valid=audit_logger.verify_chain(); s=audit_logger.summary()
    return {"valid":valid,"total":s["total"],"last_hash":s["last_hash"],"genesis_hash":s["genesis_hash"]}

def get_admin_audit_tamper(actor_id="admin"):
    """GET /admin/audit/tamper — list broken seqs."""
    audit_logger.admin_chain_verify(user_id=actor_id)
    broken=audit_logger.detect_tamper()
    return {"broken_seqs":broken,"tampered":len(broken)>0}

def get_admin_audit_export_jsonl(actor_id="admin"):
    """GET /admin/audit/export.jsonl"""
    audit_logger.admin_audit_export(user_id=actor_id)
    return audit_logger.export_jsonl()

def get_admin_audit_export_csv(actor_id="admin"):
    """GET /admin/audit/export.csv"""
    audit_logger.admin_audit_export(user_id=actor_id)
    return audit_logger.export_csv()

def get_admin_audit_events():
    """GET /admin/audit/events — 64 event types."""
    events=[]
    for ev in AuditEvent:
        meta=EVENT_META.get(ev.value,{}); sev=meta.get("severity",Severity.INFO)
        events.append({"event":ev.value,"category":meta.get("category","misc"),
                       "severity":sev.value if isinstance(sev,Severity) else sev,
                       "requires_reason":ev in REQUIRES_REASON})
    return {"events":events,"total":len(events)}

def get_admin_audit_user_trail(user_id,limit=100,actor_id="admin"):
    """GET /admin/audit/user/{user_id}"""
    audit_logger.admin_audit_export(user_id=actor_id)
    records=audit_logger.query(user_id=user_id,limit=limit)
    return {"user_id":user_id,"records":[r.to_dict() for r in records],"count":len(records)}

def post_admin_audit_test(event="auth.login.ok",user_id="test-admin",
                          tenant_id="default",reason="",actor_id="admin"):
    """POST /admin/audit/test — dev/staging only."""
    r=audit_logger.record(event=event,user_id=user_id,tenant_id=tenant_id,
                          actor_id=actor_id,reason=reason,detail={"test":True})
    return {"ok":True,"seq":r.seq,"chain_hash":r.chain_hash}

ADMIN_AUDIT_ROUTES=[
    {"method":"GET", "path":"/admin/audit/",             "handler":"get_admin_audit_list"},
    {"method":"GET", "path":"/admin/audit/summary",      "handler":"get_admin_audit_summary"},
    {"method":"GET", "path":"/admin/audit/verify",       "handler":"get_admin_audit_verify"},
    {"method":"GET", "path":"/admin/audit/tamper",       "handler":"get_admin_audit_tamper"},
    {"method":"GET", "path":"/admin/audit/export.jsonl", "handler":"get_admin_audit_export_jsonl"},
    {"method":"GET", "path":"/admin/audit/export.csv",   "handler":"get_admin_audit_export_csv"},
    {"method":"GET", "path":"/admin/audit/events",       "handler":"get_admin_audit_events"},
    {"method":"GET", "path":"/admin/audit/user/{id}",    "handler":"get_admin_audit_user_trail"},
    {"method":"POST","path":"/admin/audit/test",         "handler":"post_admin_audit_test"},
]
