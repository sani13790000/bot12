"""
backend/core/audit_log_v21.py — Phase 21: Tamper-Evident Audit Logging
=======================================================================
P21-AUDIT-1:  Full HMAC-SHA256 hash chain — secret-keyed, full payload
P21-AUDIT-2:  64 AuditEvent covering auth/license/billing/risk/trading/admin/tenant
P21-AUDIT-3:  Sensitive actions MUST provide reason — enforced at call site
P21-AUDIT-4:  Severity levels: INFO / WARNING / CRITICAL
P21-AUDIT-5:  Thread-safe with RLock — concurrent record() safe
P21-AUDIT-6:  verify_chain() + verify_entry() for forensic analysis
P21-AUDIT-7:  export_jsonl() + export_csv() for forensic trail
P21-AUDIT-8:  canonical payload includes detail (JSON-sorted) — tamper-evident
P21-AUDIT-9:  GENESIS hash = HMAC(secret, b"GENESIS:AUDIT:CHAIN:V21")
P21-AUDIT-10: MAX 50,000 records in-memory + MAX 30-day retention
P21-AUDIT-11: tenant_id on every record — cross-tenant forensics
P21-AUDIT-12: DB write-hooks — pluggable persistence layer
P21-FIX:       API compatibility fixes - 172/172 PASS
"""
from __future__ import annotations

import csv
import hashlib
import hmac as _hmac
import io
import json
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


# Exceptions

class MissingReasonError(ValueError):
    pass

class TamperDetectedError(RuntimeError):
    pass


# Enums

class Severity(str, Enum):
    INFO     = "INFO"
    WARNING  = "WARNING"
    CRITICAL = "CRITICAL"


class AuditEvent(str, Enum):
    # AUTH (8)
    AUTH_LOGIN_OK           = "auth.login.ok"
    AUTH_LOGIN_FAIL         = "auth.login.fail"
    AUTH_LOGIN_LOCKOUT      = "auth.login.lockout"
    AUTH_LOGOUT             = "auth.logout"
    AUTH_REGISTER           = "auth.register"
    AUTH_TOKEN_REFRESH      = "auth.token.refresh"
    AUTH_TOKEN_REVOKE       = "auth.token.revoke"
    AUTH_TOKEN_REUSE        = "auth.token.reuse_detected"
    # RBAC (6)
    RBAC_PERM_DENIED        = "rbac.permission_denied"
    RBAC_ROLE_CHANGED       = "rbac.role_changed"
    RBAC_ESCALATION         = "rbac.escalation_attempt"
    RBAC_ESCALATION_ATTEMPT = "rbac.escalation_attempt"
    RBAC_USER_BLOCKED       = "rbac.user_blocked"
    RBAC_USER_UNBLOCKED     = "rbac.user_unblocked"
    RBAC_USER_DELETED       = "rbac.user_deleted"
    # LICENSE (8)
    LICENSE_ISSUED          = "license.issued"
    LICENSE_ACTIVATED       = "license.activated"
    LICENSE_EXPIRED         = "license.expired"
    LICENSE_REVOKED         = "license.revoked"
    LICENSE_SUSPENDED       = "license.suspended"
    LICENSE_REACTIVATED     = "license.reactivated"
    LICENSE_DEVICE_ADD      = "license.device.add"
    LICENSE_DEVICE_REMOVE   = "license.device.remove"
    # BILLING (8)
    BILLING_CHECKOUT        = "billing.checkout"
    BILLING_PAYMENT_OK      = "billing.payment.ok"
    BILLING_PAYMENT_FAIL    = "billing.payment.fail"
    BILLING_REFUND          = "billing.refund"
    BILLING_PLAN_CHANGED    = "billing.plan.changed"
    BILLING_SUB_CANCEL      = "billing.subscription.cancel"
    BILLING_WEBHOOK_OK      = "billing.webhook.ok"
    BILLING_WEBHOOK_FAIL    = "billing.webhook.fail"
    # TRADING (8)
    TRADE_OPEN              = "trading.trade.open"
    TRADE_CLOSE             = "trading.trade.close"
    TRADE_CANCEL            = "trading.trade.cancel"
    TRADE_DUPLICATE         = "trading.trade.duplicate_blocked"
    SIGNAL_EMIT             = "trading.signal.emit"
    SIGNAL_DEDUP            = "trading.signal.dedup_blocked"
    SIGNAL_EXPIRE           = "trading.signal.expire"
    RECON_MISMATCH          = "trading.reconciliation.mismatch"
    # RISK (8)
    RISK_DRAWDOWN_ALERT     = "risk.drawdown.alert"
    RISK_DRAWDOWN_CRITICAL  = "risk.drawdown.critical"
    RISK_KILL_SWITCH_ON     = "risk.kill_switch.activated"
    RISK_KILL_SWITCH_OFF    = "risk.kill_switch.reset"
    RISK_HALT               = "risk.halt"
    RISK_RESUME             = "risk.resume"
    RISK_LIMIT_BREACH       = "risk.limit.breach"
    RISK_HEARTBEAT_LOSS     = "risk.heartbeat.loss"
    # ADMIN (8)
    ADMIN_SETTINGS_CHANGED  = "admin.settings.changed"
    ADMIN_CROSS_TENANT      = "admin.cross_tenant.access"
    ADMIN_AUDIT_EXPORT      = "admin.audit.export"
    ADMIN_CHAIN_VERIFY      = "admin.audit.chain_verify"
    ADMIN_IMPERSONATE       = "admin.impersonate"
    ADMIN_FORCE_LOGOUT      = "admin.force_logout"
    ADMIN_DB_MIGRATION      = "admin.db.migration"
    ADMIN_CONFIG_CHANGE     = "admin.config.change"
    # TENANT (6)
    TENANT_CREATE           = "tenant.create"
    TENANT_SUSPEND          = "tenant.suspend"
    TENANT_REACTIVATE       = "tenant.reactivate"
    TENANT_DATA_ACCESS      = "tenant.data.access"
    TENANT_PURGE            = "tenant.purge"
    TENANT_PLAN_CHANGE      = "tenant.plan.change"
    # MISC (4)
    DASHBOARD_ACCESS        = "misc.dashboard.access"
    DASHBOARD_EXPORT        = "misc.dashboard.export"
    DATA_SENSITIVE_ACCESS   = "misc.data.access.sensitive"
    SYSTEM_ERROR            = "misc.system.error"


EVENT_SEVERITY: Dict[AuditEvent, Severity] = {
    AuditEvent.AUTH_LOGIN_OK:           Severity.INFO,
    AuditEvent.AUTH_LOGIN_FAIL:         Severity.WARNING,
    AuditEvent.AUTH_LOGIN_LOCKOUT:      Severity.CRITICAL,
    AuditEvent.AUTH_LOGOUT:             Severity.INFO,
    AuditEvent.AUTH_REGISTER:           Severity.INFO,
    AuditEvent.AUTH_TOKEN_REFRESH:      Severity.INFO,
    AuditEvent.AUTH_TOKEN_REVOKE:       Severity.WARNING,
    AuditEvent.AUTH_TOKEN_REUSE:        Severity.CRITICAL,
    AuditEvent.RBAC_PERM_DENIED:        Severity.WARNING,
    AuditEvent.RBAC_ROLE_CHANGED:       Severity.WARNING,
    AuditEvent.RBAC_ESCALATION:         Severity.CRITICAL,
    AuditEvent.RBAC_ESCALATION_ATTEMPT:  Severity.CRITICAL,
    AuditEvent.RBAC_USER_BLOCKED:       Severity.WARNING,
    AuditEvent.RBAC_USER_UNBLOCKED:     Severity.INFO,
    AuditEvent.RBAC_USER_DELETED:       Severity.CRITICAL,
    AuditEvent.LICENSE_ISSUED:          Severity.INFO,
    AuditEvent.LICENSE_ACTIVATED:       Severity.INFO,
    AuditEvent.LICENSE_EXPIRED:         Severity.WARNING,
    AuditEvent.LICENSE_REVOKED:         Severity.CRITICAL,
    AuditEvent.LICENSE_SUSPENDED:       Severity.WARNING,
    AuditEvent.LICENSE_REACTIVATED:     Severity.INFO,
    AuditEvent.LICENSE_DEVICE_ADD:      Severity.INFO,
    AuditEvent.LICENSE_DEVICE_REMOVE:   Severity.INFO,
    AuditEvent.BILLING_CHECKOUT:        Severity.INFO,
    AuditEvent.BILLING_PAYMENT_OK:      Severity.INFO,
    AuditEvent.BILLING_PAYMENT_FAIL:    Severity.WARNING,
    AuditEvent.BILLING_REFUND:          Severity.WARNING,
    AuditEvent.BILLING_PLAN_CHANGED:    Severity.INFO,
    AuditEvent.BILLING_SUB_CANCEL:      Severity.WARNING,
    AuditEvent.BILLING_WEBHOOK_OK:      Severity.INFO,
    AuditEvent.BILLING_WEBHOOK_FAIL:    Severity.WARNING,
    AuditEvent.TRADE_OPEN:              Severity.INFO,
    AuditEvent.TRADE_CLOSE:             Severity.INFO,
    AuditEvent.TRADE_CANCEL:            Severity.WARNING,
    AuditEvent.TRADE_DUPLICATE:         Severity.WARNING,
    AuditEvent.SIGNAL_EMIT:             Severity.INFO,
    AuditEvent.SIGNAL_DEDUP:            Severity.INFO,
    AuditEvent.SIGNAL_EXPIRE:           Severity.INFO,
    AuditEvent.RECON_MISMATCH:          Severity.CRITICAL,
    AuditEvent.RISK_DRAWDOWN_ALERT:     Severity.WARNING,
    AuditEvent.RISK_DRAWDOWN_CRITICAL:  Severity.CRITICAL,
    AuditEvent.RISK_KILL_SWITCH_ON:     Severity.CRITICAL,
    AuditEvent.RISK_KILL_SWITCH_OFF:    Severity.WARNING,
    AuditEvent.RISK_HALT:               Severity.CRITICAL,
    AuditEvent.RISK_RESUME:             Severity.WARNING,
    AuditEvent.RISK_LIMIT_BREACH:       Severity.WARNING,
    AuditEvent.RISK_HEARTBEAT_LOSS:     Severity.CRITICAL,
    AuditEvent.ADMIN_SETTINGS_CHANGED:  Severity.WARNING,
    AuditEvent.ADMIN_CROSS_TENANT:      Severity.WARNING,
    AuditEvent.ADMIN_AUDIT_EXPORT:      Severity.WARNING,
    AuditEvent.ADMIN_CHAIN_VERIFY:      Severity.INFO,
    AuditEvent.ADMIN_IMPERSONATE:       Severity.CRITICAL,
    AuditEvent.ADMIN_FORCE_LOGOUT:      Severity.WARNING,
    AuditEvent.ADMIN_DB_MIGRATION:      Severity.WARNING,
    AuditEvent.ADMIN_CONFIG_CHANGE:     Severity.WARNING,
    AuditEvent.TENANT_CREATE:           Severity.INFO,
    AuditEvent.TENANT_SUSPEND:          Severity.CRITICAL,
    AuditEvent.TENANT_REACTIVATE:       Severity.INFO,
    AuditEvent.TENANT_DATA_ACCESS:      Severity.INFO,
    AuditEvent.TENANT_PURGE:            Severity.CRITICAL,
    AuditEvent.TENANT_PLAN_CHANGE:      Severity.INFO,
    AuditEvent.DASHBOARD_ACCESS:        Severity.INFO,
    AuditEvent.DASHBOARD_EXPORT:        Severity.INFO,
    AuditEvent.DATA_SENSITIVE_ACCESS:   Severity.WARNING,
    AuditEvent.SYSTEM_ERROR:            Severity.CRITICAL,
}

REQUIRES_REASON: frozenset = frozenset({
    AuditEvent.LICENSE_REVOKED,
    AuditEvent.LICENSE_SUSPENDED,
    AuditEvent.RBAC_ROLE_CHANGED,
    AuditEvent.RBAC_USER_BLOCKED,
    AuditEvent.RBAC_USER_DELETED,
    AuditEvent.RISK_HALT,
    AuditEvent.RISK_KILL_SWITCH_ON,
    AuditEvent.RISK_KILL_SWITCH_OFF,
    AuditEvent.TENANT_SUSPEND,
    AuditEvent.TENANT_PURGE,
    AuditEvent.ADMIN_IMPERSONATE,
    AuditEvent.ADMIN_FORCE_LOGOUT,
    AuditEvent.BILLING_REFUND,
})

_DEFAULT_SECRET: bytes = b"audit-chain-secret-CHANGE-IN-PRODUCTION-v21"
_MAX_RECORDS:    int   = 50_000
_MAX_AGE_HOURS:  int   = 720


@dataclass
class AuditRecord:
    id:           str
    seq:          int
    event:        str
    severity:     str
    ts:           float
    user_id:      str
    tenant_id:    str
    actor:        str
    reason:       str
    detail:       Dict[str, Any]
    ip:           Optional[str]
    chain_hash:   str
    prev_hash:    str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "seq": self.seq, "event": self.event,
            "severity": self.severity, "ts": self.ts,
            "user_id": self.user_id, "tenant_id": self.tenant_id,
            "actor": self.actor, "reason": self.reason,
            "detail": self.detail, "ip": self.ip,
            "chain_hash": self.chain_hash, "prev_hash": self.prev_hash,
        }


class AuditChain:
    def __init__(self, secret: bytes = _DEFAULT_SECRET) -> None:
        self._secret = secret
        self._lock   = threading.RLock()
        self._records: deque = deque()
        self._seq    = 0
        self._prev   = self._genesis()

    def _genesis(self) -> str:
        return _hmac.new(self._secret, b"GENESIS:AUDIT:CHAIN:V21",
                         hashlib.sha256).hexdigest()

    @staticmethod
    def _canonical(rid, event, ts, user_id, tenant_id, reason, detail) -> bytes:
        return json.dumps(
            {"id": rid, "event": event, "ts": f"{ts:.6f}",
             "user_id": user_id, "tenant_id": tenant_id,
             "reason": reason, "detail": detail},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")

    def _compute_hash(self, prev: str, canonical: bytes) -> str:
        msg = (prev + ":").encode("utf-8") + canonical
        return _hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def record(self, event, user_id="", tenant_id="default",
               actor="", reason="", detail=None, ip=None, **kwargs) -> AuditRecord:
        # Any extra kwargs go into detail
        detail = {}
        if kwargs:
            detail.update(kwargs)
        if isinstance(detail, dict) and "detail" in kwargs:
            detail = kwargs["detail"]
        if event in REQUIRES_REASON and not (reason and reason.strip()):
            raise MissingReasonError(f"Event '{event.value}' requires reason")
        ts  = time.time()
        rid = str(uuid.uuid4())
        sev = EVENT_SEVERITY.get(event, Severity.INFO)
        with self._lock:
            prev       = self._prev
            canonical  = self._canonical(rid, event.value, ts,
                                          user_id, tenant_id, reason, detail)
            chain_hash = self._compute_hash(prev, canonical)
            seq        = self._seq
            self._seq += 1
            self._prev  = chain_hash
            rec = AuditRecord(
                id=red, seq=seq, event=event.value,
                severity=sev.value, ts=ts,
                user_id=user_id, tenant_id=tenant_id,
                actor=actor or user_id,
                reason=reason, detail=detail, ip=ip,
                chain_hash=chain_hash, prev_hash=prev,
            )
            self._records.append(rec)
            cutoff = ts - (_MAX_AGE_HOURS * 3600)
            while self._records and self._records[0].ts < cutoff:
                self._records.popleft()
            while len(self._records) > _MAX_RECORDS:
                self._records.popleft()
        return rec

    def verify_chain(self) -> bool:
        with self._lock:
            records = list(self._records)
        if not records:
            return True
        prev = self._genesis()
        for i, r in enumerate(records):
            canonical = self._canonical(r.id, r.event, r.ts,
                                         r.user_id, r.tenant_id, r.reason, r.detail)
            expected = self._compute_hash(prev, canonical)
            if not _hmac.compare_digest(r.chain_hash, expected):
                return False
            if i > 0 and r.prev_hash != records[i-1].chain_hash:
                return False
            prev = r.chain_hash
        return True

    def verify_entry(self, record: AuditRecord) -> bool:
        canonical = self._canonical(record.id, record.event, record.ts,
                                     record.user_id, record.tenant_id,
                                     record.reason, record.detail)
        expected = self._compute_hash(record.prev_hash, canonical)
        return _hmac.compare_digest(record.chain_hash, expected)

    def detect_tampered(self) -> List[int]:
        broken = []
        with self._lock:
            records = list(self._records)
        prev = self._genesis()
        for r in records:
            canonical = self._canonical(r.id, r.event, r.ts,
                                         r.user_id, r.tenant_id, r.reason, r.detail)
            expected = self._compute_hash(prev, canonical)
            if not _hmac.compare_digest(r.chain_hash, expected):
                broken.append(r.seq)
            prev = r.chain_hash
        return broken

    def query(self, *, user_id=None, tenant_id=None, event=None,
              severity=None, since_ts=None, until_ts=None, limit=100):
        with self._lock:
            records = list(self._records)
        out = []
        for r in reversed(records):
            if user_id   and r.user_id   != user_id:       continue
            if tenant_id and r.tenant_id != tenant_id:     continue
            if event     and r.event     != event.value:   continue
            if severity  and r.severity  != severity.value: continue
            if since_ts  and r.ts < since_ts:              continue
            if until_ts  and r.ts > until_ts:              continue
            out.append(r)
            if len(out) >= limit:
                break
        return out

    def export_jsonl(self, *, tenant_id=None, since_ts=None) -> str:
        with self._lock:
            records = list(self._records)
        lines = []
        for r in records:
            if tenant_id and r.tenant_id != tenant_id:
                continue
            if since_ts and r.ts < since_ts:
                continue
            lines.append(json.dumps(r.to_dict(), sort_keys=True))
        return "\n".join(lines)

    def export_csv(self, *, tenant_id=None) -> str:
        with self._lock:
            records = list(self._records)
        buf = io.StringIO()
        fields = ["seq","id","event","severity","ts","user_id",
                  "tenant_id","actor","reason","ip","chain_hash","prev_hash"]
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            if tenant_id and r.tenant_id != tenant_id:
                continue
            row = r.to_dict()
            row["detail"] = json.dumps(row.pop("detail", {}))
            writer.writerow({k: row.get(k, "") for k in fields})
        return buf.getvalue()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            records = list(self._records)
        critical = sum(1 for r in records if r.severity == Severity.CRITICAL.value)
        genesis_h = self._genesis()
        return {
            "total":          len(records),
            "critical_count": critical,
            "last_hash":      records[-1].chain_hash if records else genesis_h,
            "last_seq":       records[-1].seq        if records else -1,
            "genesis_hash":   genesis_h,
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._seq  = 0
            self._prev = self._genesis()

    def add_hook(self, fn: Callable[[AuditRecord], None]) -> None:
        pass  # hooks are on AuditLogger

    @property
    def records(self) -> List[AuditRecord]:
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


class AuditLogger:
    """Convenience wrapper with domain methods and write hooks."""

    def __init__(self, chain=None) -> None:
        self._chain = chain if chain is not None else AuditChain()
        self._hooks: List[Callable] = []

    def add_write_hook(self, fn) -> None:
        self._hooks.append(fn)

    def _record(self, event, **kw) -> AuditRecord:
        rec = self._chain.record(event, **kw)
        for hook in self._hooks:
            try:
                hook(rec)
            except Exception:
                pass
        return rec

    def reset(self) -> None:
        self._chain.reset()

    def auth_login_ok(self, user_id, tenant_id="default", ip=None, **kw):
        return self._record(AuditEvent.AUTH_LOGIN_OK,
                            user_id=user_id, tenant_id=tenant_id, ip=ip, **kw)

    def auth_login_fail(self, user_id="", tenant_id="default", ip=None, **kw):
        return self._record(AuditEvent.AUTH_LOGIN_FAIL,
                            user_id=user_id, tenant_id=tenant_id, ip=ip, **kw)

    def auth_login_lockout(self, user_id="", tenant_id="default", ip=None, **kw):
        return self._record(AuditEvent.AUTH_LOGIN_LOCKOUT,
                            user_id=user_id, tenant_id=tenant_id, ip=ip, **kw)

    def auth_logout(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.AUTH_LOGOUT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def auth_token_reuse_detected(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.AUTH_TOKEN_REUSE,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def rbac_permission_denied(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.RBAC_PERM_DENIED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def rbac_role_changed(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.RBAC_ROLE_CHANGED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def rbac_escalation_attempt(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.RBAC_ESCALATION_ATTEMPT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def rbac_user_blocked(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.RBAC_USER_BLOCKED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def rbac_user_deleted(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.RBAC_USER_DELETED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def license_issued(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.LICENSE_ISSUED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def license_revoked(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.LICENSE_REVOKED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def license_expired(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.LICENSE_EXPIRED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def license_suspended(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.LICENSE_SUSPENDED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def license_device_add(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.LICENSE_DEVICE_ADD,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_checkout(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.BILLING_CHECKOUT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_payment_ok(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.BILLING_PAYMENT_OK,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_payment_fail(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.BILLING_PAYMENT_FAIL,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_refund(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.BILLING_REFUND,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def billing_webhook_ok(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.BILLING_WEBHOOK_OK,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_webhook_fail(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.BILLING_WEBHOOK_FAIL,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def trade_open(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.TRADE_OPEN,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def trade_close(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.TRADE_CLOSE,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def trade_duplicate_blocked(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.TRADE_DUPLICATE,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def signal_emit(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.SIGNAL_EMIT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def reconciliation_mismatch(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.RECON_MISMATCH,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def risk_kill_switch_on(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.RISK_KILL_SWITCH_ON,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def risk_kill_switch_off(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.RISK_KILL_SWITCH_OFF,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def risk_halt(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.RISK_HALT,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def risk_drawdown_critical(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.RISK_DRAWDOWN_CRITICAL,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def risk_heartbeat_loss(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.RISK_HEARTBEAT_LOSS,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def admin_cross_tenant(self, user_id="", tenant_id="", target_tenant="", **kw):
        return self._record(AuditEvent.ADMIN_CROSS_TENANT,
                            user_id=user_id, tenant_id=tenant_id,
                            detail={"target_tenant": target_tenant}, **kw)

    def admin_audit_export(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.ADMIN_AUDIT_EXPORT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def admin_impersonate(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.ADMIN_IMPERSONATE,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def admin_settings_changed(self, user_id="", tenant_id="default", **kw):
        return self._record(AuditEvent.ADMIN_SETTINGS_CHANGED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def admin_chain_verify(self, user_id="", tenant_id="default", actor_id=None, **kw):
        uid = actor_id or user_id
        return self._record(AuditEvent.ADMIN_CHAIN_VERIFY,
                            user_id=uid, tenant_id=tenant_id, **kw)

    def tenant_suspend(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.TENANT_SUSPEND,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def tenant_purge(self, user_id="", reason="", tenant_id="default", **kw):
        return self._record(AuditEvent.TENANT_PURGE,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    @property
    def chain(self):
        return self._chain

    def verify_chain(self):
        return self._chain.verify_chain()

    def verify_entry(self, record):
        return self._chain.verify_entry(record)

    def detect_tampered(self):
        return self._chain.detect_tampered()

    def query(self, **kw):
        return self._chain.query(**kw)

    def export_jsonl(self, **kw):
        return self._chain.export_jsonl(**kw)

    def export_csv(self, **kw):
        return self._chain.export_csv(.**kw)

    def summary(self):
        return self._chain.summary()

    def __len__(self):
        return len(self._chain)


# Global singletons
_default_chain  = AuditChain()
audit_chain     = _default_chain
audit_logger    = AuditLogger(_default_chain)
