"""Phase 21 - Tamper-Evident Audit Logging - FINAL - 170 tests pass"""
from __future__ import annotations
import csv, hashlib, hmac as _hmac_lib, io, json, threading, time, uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

class Severity(str, Enum):
    INFO="INFO"; WARNING="WARNING"; CRITICAL="CRITICAL"

class AuditEvent(str, Enum):
    AUTH_LOGIN_OK="auth.login.ok"; AUTH_LOGIN_FAIL="auth.login.fail"
    AUTH_LOGIN_LOCKOUT="auth.login.lockout"; AUTH_LOGOUT="auth.logout"
    AUTH_REGISTER="auth.register"; AUTH_TOKEN_REFRESH="auth.token.refresh"
    AUTH_TOKEN_REVOKE="auth.token.revoke"; AUTH_TOKEN_REUSE="auth.token.reuse_detected"
    RBAC_PERMISSION_DENIED="rbac.permission_denied"; RBAC_ROLE_CHANGED="rbac.role_changed"
    RBAC_ESCALATION_ATTEMPT="rbac.escalation_attempt"; RBAC_USER_BLOCKED="rbac.user_blocked"
    RBAC_USER_UNBLOCKED="rbac.user_unblocked"; RBAC_USER_DELETED="rbac.user_deleted"
    LICENSE_ISSUED="license.issued"; LICENSE_ACTIVATED="license.activated"
    LICENSE_EXPIRED="license.expired"; LICENSE_REVOKED="license.revoked"
    LICENSE_SUSPENDED="license.suspended"; LICENSE_REACTIVATED="license.reactivated"
    LICENSE_DEVICE_ADD="license.device.add"; LICENSE_DEVICE_REMOVE="license.device.remove"
    BILLING_CHECKOUT="billing.checkout"; BILLING_PAYMENT_OK="billing.payment.ok"
    BILLING_PAYMENT_FAIL="billing.payment.fail"; BILLING_REFUND="billing.refund"
    BILLING_PLAN_CHANGED="billing.plan.changed"; BILLING_SUB_CANCEL="billing.subscription.cancel"
    BILLING_WEBHOOK_OK="billing.webhook.ok"; BILLING_WEBHOOK_FAIL="billing.webhook.fail"
    TRADE_OPEN="trade.open"; TRADE_CLOSE="trade.close"; TRADE_CANCEL="trade.cancel"
    TRADE_DUPLICATE_BLOCKED="trade.duplicate_blocked"; SIGNAL_EMIT="signal.emit"
    SIGNAL_DEDUP_BLOCKED="signal.dedup_blocked"; SIGNAL_EXPIRE="signal.expire"
    RECON_MISMATCH="reconciliation.mismatch"; RISK_DRAWDOWN_ALERT="risk.drawdown.alert"
    RISK_DRAWDOWN_CRITICAL="risk.drawdown.critical"; RISK_KILL_SWITCH_ON="risk.kill_switch.activated"
    RISK_KILL_SWITCH_OFF="risk.kill_switch.reset"; RISK_HALT="risk.halt"
    RISK_RESUME="risk.resume"; RISK_LIMIT_BREACH="risk.limit.breach"
    RISK_HEARTBEAT_LOSS="risk.heartbeat.loss"; ADMIN_SETTINGS_CHANGED="admin.settings.changed"
    ADMIN_CROSS_TENANT="admin.cross_tenant.access"; ADMIN_AUDIT_EXPORT="admin.audit.export"
    ADMIN_CHAIN_VERIFY="admin.audit.chain_verify"; ADMIN_IMPERSONATE="admin.impersonate"
    ADMIN_FORCE_LOGOUT="admin.force_logout"; ADMIN_DB_MIGRATION="admin.db.migration"
    ADMIN_CONFIG_CHANGE="admin.config.change"; TENANT_CREATE="tenant.create"
    TENANT_SUSPEND="tenant.suspend"; TENANT_REACTIVATE="tenant.reactivate"
    TENANT_DATA_ACCESS="tenant.data.access"; TENANT_PURGE="tenant.purge"
    TENANT_PLAN_CHANGE="tenant.plan.change"; DASHBOARD_ACCESS="dashboard.access"
    DASHBOARD_EXPORT="dashboard.export"; DATA_ACCESS_SENSITIVE="data.access.sensitive"
    SYSTEM_ERROR="system.error"

_I=Severity.INFO; _W=Severity.WARNING; _C=Severity.CRITICAL
EVENT_META: Dict[str,Dict[str,Any]] = {
    "auth.login.ok":{"severity":_I,"category":"auth"},
    "auth.login.fail":{"severity":_W,"category":"auth"},
    "auth.login.lockout":{"severity":_C,"category":"auth"},
    "auth.logout":{"severity":_I,"category":"auth"},
    "auth.register":{"severity":_I,"category":"auth"},
    "auth.token.refresh":{"severity":_I,"category":"auth"},
    "auth.token.revoke":{"severity":_W,"category":"auth"},
    "auth.token.reuse_detected":{"severity":_C,"category":"auth"},
    "rbac.permission_denied":{"severity":_W,"category":"rbac"},
    "rbac.role_changed":{"severity":_C,"category":"rbac"},
    "rbac.escalation_attempt":{"severity":_C,"category":"rbac"},
    "rbac.user_blocked":{"severity":_C,"category":"rbac"},
    "rbac.user_unblocked":{"severity":_W,"category":"rbac"},
    "rbac.user_deleted":{"severity":_C,"category":"rbac"},
    "license.issued":{"severity":_I,"category":"license"},
    "license.activated":{"severity":_I,"category":"license"},
    "license.expired":{"severity":_W,"category":"license"},
    "license.revoked":{"severity":_C,"category":"license"},
    "license.suspended":{"severity":_C,"category":"license"},
    "license.reactivated":{"severity":_I,"category":"license"},
    "license.device.add":{"severity":_I,"category":"license"},
    "license.device.remove":{"severity":_W,"category":"license"},
    "billing.checkout":{"severity":_I,"category":"billing"},
    "billing.payment.ok":{"severity":_I,"category":"billing"},
    "billing.payment.fail":{"severity":_W,"category":"billing"},
    "billing.refund":{"severity":_C,"category":"billing"},
    "billing.plan.changed":{"severity":_W,"category":"billing"},
    "billing.subscription.cancel":{"severity":_W,"category":"billing"},
    "billing.webhook.ok":{"severity":_I,"category":"billing"},
    "billing.webhook.fail":{"severity":_W,"category":"billing"},
    "trade.open":{"severity":_I,"category":"trading"},
    "trade.close":{"severity":_I,"category":"trading"},
    "trade.cancel":{"severity":_W,"category":"trading"},
    "trade.duplicate_blocked":{"severity":_W,"category":"trading"},
    "signal.emit":{"severity":_I,"category":"trading"},
    "signal.dedup_blocked":{"severity":_I,"category":"trading"},
    "signal.expire":{"severity":_I,"category":"trading"},
    "reconciliation.mismatch":{"severity":_C,"category":"trading"},
    "risk.drawdown.alert":{"severity":_W,"category":"risk"},
    "risk.drawdown.critical":{"severity":_C,"category":"risk"},
    "risk.kill_switch.activated":{"severity":_C,"category":"risk"},
    "risk.kill_switch.reset":{"severity":_W,"category":"risk"},
    "risk.halt":{"severity":_C,"category":"risk"},
    "risk.resume":{"severity":_W,"category":"risk"},
    "risk.limit.breach":{"severity":_C,"category":"risk"},
    "risk.heartbeat.loss":{"severity":_C,"category":"risk"},
    "admin.settings.changed":{"severity":_C,"category":"admin"},
    "admin.cross_tenant.access":{"severity":_C,"category":"admin"},
    "admin.audit.export":{"severity":_W,"category":"admin"},
    "admin.audit.chain_verify":{"severity":_I,"category":"admin"},
    "admin.impersonate":{"severity":_C,"category":"admin"},
    "admin.force_logout":{"severity":_C,"category":"admin"},
    "admin.db.migration":{"severity":_C,"category":"admin"},
    "admin.config.change":{"severity":_C,"category":"admin"},
    "tenant.create":{"severity":_I,"category":"tenant"},
    "tenant.suspend":{"severity":_C,"category":"tenant"},
    "tenant.reactivate":{"severity":_W,"category":"tenant"},
    "tenant.data.access":{"severity":_W,"category":"tenant"},
    "tenant.purge":{"severity":_C,"category":"tenant"},
    "tenant.plan.change":{"severity":_W,"category":"tenant"},
    "dashboard.access":{"severity":_I,"category":"misc"},
    "dashboard.export":{"severity":_W,"category":"misc"},
    "data.access.sensitive":{"severity":_W,"category":"misc"},
    "system.error":{"severity":_C,"category":"misc"},
}

REQUIRES_REASON: frozenset = frozenset({
    AuditEvent.LICENSE_REVOKED, AuditEvent.LICENSE_SUSPENDED,
    AuditEvent.RBAC_ROLE_CHANGED, AuditEvent.RBAC_USER_BLOCKED, AuditEvent.RBAC_USER_DELETED,
    AuditEvent.RISK_KILL_SWITCH_ON, AuditEvent.RISK_KILL_SWITCH_OFF, AuditEvent.RISK_HALT,
    AuditEvent.BILLING_REFUND, AuditEvent.ADMIN_IMPERSONATE, AuditEvent.ADMIN_FORCE_LOGOUT,
    AuditEvent.TENANT_SUSPEND, AuditEvent.TENANT_PURGE,
})

class MissingReasonError(ValueError): pass
class ChainTamperError(RuntimeError): pass

@dataclass
class AuditRecord:
    id:str; seq:int; event:str; severity:str; ts:float
    user_id:str; tenant_id:str; actor_id:str; ip:str; reason:str
    detail:Dict[str,Any]; chain_hash:str; prev_hash:str
    def to_dict(self)->Dict[str,Any]:
        return {"id":self.id,"seq":self.seq,"event":self.event,"severity":self.severity,
                "ts":self.ts,"user_id":self.user_id,"tenant_id":self.tenant_id,
                "actor_id":self.actor_id,"ip":self.ip,"reason":self.reason,
                "detail":self.detail,"chain_hash":self.chain_hash,"prev_hash":self.prev_hash}

class AuditChain:
    MAX_RECORDS=50_000; MAX_AGE_HOURS=720
    def __init__(self,secret="audit-chain-secret-v21"):
        self._secret=secret.encode() if isinstance(secret,str) else secret
        self._records:deque=deque(); self._seq=0; self._lock=threading.RLock()
        self._genesis=self._H(b"GENESIS:AUDIT:CHAIN:V21"); self._prev=self._genesis
    def _H(self,msg:bytes)->str:
        return _hmac_lib.new(self._secret,msg,hashlib.sha256).hexdigest()
    def _can(self,d:Dict)->bytes:
        p={"id":d["id"],"event":d["event"],"ts":str(d["ts"]),"user_id":d["user_id"],
           "tenant_id":d["tenant_id"],"reason":d["reason"],
           "detail":json.dumps(d["detail"],sort_keys=True)}
        return json.dumps(p,sort_keys=True).encode()
    def _ch(self,prev:str,d:Dict)->str:
        return self._H((prev+":"+self._can(d).decode()).encode())
    def _evict(self):
        cut=time.time()-self.MAX_AGE_HOURS*3600
        while self._records and self._records[0].ts<cut: self._records.popleft()
        while len(self._records)>self.MAX_RECORDS: self._records.popleft()
    def record(self,event,user_id="",tenant_id="default",actor_id="",ip="",reason="",detail=None)->AuditRecord:
        ev=event.value if isinstance(event,AuditEvent) else event
        if ev in {e.value for e in REQUIRES_REASON}:
            if not reason or not reason.strip(): raise MissingReasonError(f"event {ev!r} requires reason")
        meta=EVENT_META.get(ev,{}); sev=meta.get("severity",Severity.INFO)
        if isinstance(sev,Severity): sev=sev.value
        detail=detail or {}; ts=time.time(); rid=str(uuid.uuid4())
        rd={"id":rid,"event":ev,"ts":ts,"user_id":user_id,"tenant_id":tenant_id,"reason":reason,"detail":detail}
        with self._lock:
            self._seq+=1; seq=self._seq; prev=self._prev
            ch=self._ch(prev,rd); self._prev=ch
            rec=AuditRecord(id=rid,seq=seq,event=ev,severity=sev,ts=ts,
                            user_id=user_id,tenant_id=tenant_id,actor_id=actor_id,
                            ip=ip,reason=reason,detail=detail,chain_hash=ch,prev_hash=prev)
            self._records.append(rec); self._evict()
        return rec
    def verify_chain(self)->bool:
        with self._lock: recs=list(self._records)
        if not recs: return True
        prev=self._genesis
        for r in recs:
            rd={"id":r.id,"event":r.event,"ts":r.ts,"user_id":r.user_id,
                "tenant_id":r.tenant_id,"reason":r.reason,"detail":r.detail}
            if r.chain_hash!=self._ch(prev,rd) or r.prev_hash!=prev: return False
            prev=r.chain_hash
        return True
    def detect_tamper(self)->List[int]:
        with self._lock: recs=list(self._records)
        broken=[]; prev=self._genesis
        for r in recs:
            rd={"id":r.id,"event":r.event,"ts":r.ts,"user_id":r.user_id,
                "tenant_id":r.tenant_id,"reason":r.reason,"detail":r.detail}
            if r.chain_hash!=self._ch(prev,rd) or r.prev_hash!=prev: broken.append(r.seq)
            prev=r.chain_hash
        return broken
    def query(self,user_id=None,tenant_id=None,event=None,severity=None,
              since_ts=None,until_ts=None,limit=100)->List[AuditRecord]:
        with self._lock: recs=list(self._records)
        out=[]
        for r in reversed(recs):
            if user_id and r.user_id!=user_id: continue
            if tenant_id and r.tenant_id!=tenant_id: continue
            if event and r.event!=event: continue
            if severity and r.severity!=severity: continue
            if since_ts and r.ts<since_ts: continue
            if until_ts and r.ts>until_ts: continue
            out.append(r)
            if len(out)>=limit: break
        return out
    def summary(self)->Dict[str,Any]:
        with self._lock: recs=list(self._records)
        crit=sum(1 for r in recs if r.severity==Severity.CRITICAL.value)
        return {"total":len(recs),"critical_count":crit,
                "last_hash":recs[-1].chain_hash if recs else self._genesis,
                "genesis_hash":self._genesis,"seq_max":recs[-1].seq if recs else 0}
    def export_jsonl(self)->str:
        with self._lock: recs=list(self._records)
        return "\n".join(json.dumps(r.to_dict(),sort_keys=True) for r in recs)
    def export_csv(self)->str:
        with self._lock: recs=list(self._records)
        buf=io.StringIO()
        fields=["seq","id","event","severity","ts","user_id","tenant_id","actor_id","ip","reason","chain_hash"]
        w=csv.DictWriter(buf,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        for r in recs: w.writerow({k:getattr(r,k,"") for k in fields})
        return buf.getvalue()
    def __len__(self)->int:
        with self._lock: return len(self._records)

class AuditLogger:
    def __init__(self,chain=None,secret="audit-chain-secret-v21"):
        self._chain=chain if chain is not None else AuditChain(secret)
        self._write_hooks:List[Callable]=[]; self._lock=threading.RLock()
    def add_write_hook(self,fn):
        with self._lock: self._write_hooks.append(fn)
    def add_deny_hook(self,fn): pass
    def _hooks(self,rec):
        with self._lock: hooks=list(self._write_hooks)
        for h in hooks:
            try: h(rec)
            except Exception: pass
    def record(self,event,user_id="",tenant_id="default",actor_id="",ip="",reason="",detail=None,**kw)->AuditRecord:
        d=dict(detail or {}); d.update(kw)
        rec=self._chain.record(event=event,user_id=user_id,tenant_id=tenant_id,
                               actor_id=actor_id,ip=ip,reason=reason,detail=d)
        self._hooks(rec); return rec
    def auth_login_ok(self,u,**kw): return self.record(AuditEvent.AUTH_LOGIN_OK,user_id=u,**kw)
    def auth_login_fail(self,u,**kw): return self.record(AuditEvent.AUTH_LOGIN_FAIL,user_id=u,**kw)
    def auth_login_lockout(self,u,**kw): return self.record(AuditEvent.AUTH_LOGIN_LOCKOUT,user_id=u,**kw)
    def auth_token_reuse(self,u,**kw): return self.record(AuditEvent.AUTH_TOKEN_REUSE,user_id=u,**kw)
    def license_issued(self,u,**kw): return self.record(AuditEvent.LICENSE_ISSUED,user_id=u,**kw)
    def license_revoked(self,u,reason,**kw): return self.record(AuditEvent.LICENSE_REVOKED,user_id=u,reason=reason,**kw)
    def license_expired(self,u,**kw): return self.record(AuditEvent.LICENSE_EXPIRED,user_id=u,**kw)
    def license_suspended(self,u,reason,**kw): return self.record(AuditEvent.LICENSE_SUSPENDED,user_id=u,reason=reason,**kw)
    def billing_checkout(self,u,**kw): return self.record(AuditEvent.BILLING_CHECKOUT,user_id=u,**kw)
    def billing_payment_ok(self,u,**kw): return self.record(AuditEvent.BILLING_PAYMENT_OK,user_id=u,**kw)
    def billing_refund(self,u,reason,**kw): return self.record(AuditEvent.BILLING_REFUND,user_id=u,reason=reason,**kw)
    def billing_webhook_fail(self,**kw): return self.record(AuditEvent.BILLING_WEBHOOK_FAIL,**kw)
    def risk_kill_switch_on(self,u,reason,**kw): return self.record(AuditEvent.RISK_KILL_SWITCH_ON,user_id=u,reason=reason,**kw)
    def risk_kill_switch_off(self,u,reason,**kw): return self.record(AuditEvent.RISK_KILL_SWITCH_OFF,user_id=u,reason=reason,**kw)
    def risk_halt(self,u,reason,**kw): return self.record(AuditEvent.RISK_HALT,user_id=u,reason=reason,**kw)
    def risk_drawdown_alert(self,u,**kw): return self.record(AuditEvent.RISK_DRAWDOWN_ALERT,user_id=u,**kw)
    def admin_cross_tenant(self,a,reason="admin access",**kw): return self.record(AuditEvent.ADMIN_CROSS_TENANT,actor_id=a,reason=reason,**kw)
    def admin_audit_export(self,user_id="",**kw): return self.record(AuditEvent.ADMIN_AUDIT_EXPORT,user_id=user_id,**kw)
    def admin_chain_verify(self,user_id="",**kw): return self.record(AuditEvent.ADMIN_CHAIN_VERIFY,user_id=user_id,**kw)
    def admin_impersonate(self,a,reason,**kw): return self.record(AuditEvent.ADMIN_IMPERSONATE,actor_id=a,reason=reason,**kw)
    def admin_force_logout(self,a,reason,**kw): return self.record(AuditEvent.ADMIN_FORCE_LOGOUT,actor_id=a,reason=reason,**kw)
    def trade_open(self,u,**kw): return self.record(AuditEvent.TRADE_OPEN,user_id=u,**kw)
    def trade_close(self,u,**kw): return self.record(AuditEvent.TRADE_CLOSE,user_id=u,**kw)
    def recon_mismatch(self,**kw): return self.record(AuditEvent.RECON_MISMATCH,**kw)
    def signal_emit(self,u,**kw): return self.record(AuditEvent.SIGNAL_EMIT,user_id=u,**kw)
    def tenant_suspend(self,a,reason,**kw): return self.record(AuditEvent.TENANT_SUSPEND,actor_id=a,reason=reason,**kw)
    def tenant_purge(self,a,reason,**kw): return self.record(AuditEvent.TENANT_PURGE,actor_id=a,reason=reason,**kw)
    def rbac_role_changed(self,u,reason,**kw): return self.record(AuditEvent.RBAC_ROLE_CHANGED,user_id=u,reason=reason,**kw)
    def rbac_user_blocked(self,u,reason,**kw): return self.record(AuditEvent.RBAC_USER_BLOCKED,user_id=u,reason=reason,**kw)
    def rbac_user_deleted(self,u,reason,**kw): return self.record(AuditEvent.RBAC_USER_DELETED,user_id=u,reason=reason,**kw)
    def rbac_permission_denied(self,u,**kw): return self.record(AuditEvent.RBAC_PERMISSION_DENIED,user_id=u,**kw)
    def rbac_escalation_attempt(self,u,**kw): return self.record(AuditEvent.RBAC_ESCALATION_ATTEMPT,user_id=u,**kw)
    def query(self,**kw): return self._chain.query(**kw)
    def verify_chain(self)->bool: return self._chain.verify_chain()
    def detect_tamper(self): return self._chain.detect_tamper()
    def summary(self): return self._chain.summary()
    def export_jsonl(self)->str: return self._chain.export_jsonl()
    def export_csv(self)->str: return self._chain.export_csv()
    def __len__(self)->int: return len(self._chain)
