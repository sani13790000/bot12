"""Phase 21 — Tamper-Evident Audit Logging"""
from __future__ import annotations
import csv, hashlib, hmac as _hmac, io, json, threading, time, uuid
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

class MissingReasonError(ValueError): pass
class TamperDetectedError(RuntimeError): pass

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
    TRADE_DUPLICATE_BLOCKED="trade.duplicate_blocked"
    SIGNAL_EMIT="signal.emit"; SIGNAL_DEDUP_BLOCKED="signal.dedup_blocked"; SIGNAL_EXPIRE="signal.expire"
    RECON_MISMATCH="reconciliation.mismatch"
    RISK_DRAWDOWN_ALERT="risk.drawdown.alert"; RISK_DRAWDOWN_CRITICAL="risk.drawdown.critical"
    RISK_KILL_SWITCH_ON="risk.kill_switch.activated"; RISK_KILL_SWITCH_OFF="risk.kill_switch.reset"
    RISK_HALT="risk.halt"; RISK_RESUME="risk.resume"
    RISK_LIMIT_BREACH="risk.limit.breach"; RISK_HEARTBEAT_LOSS="risk.heartbeat.loss"
    ADMIN_SETTINGS_CHANGED="admin.settings.changed"; ADMIN_CROSS_TENANT="admin.cross_tenant.access"
    ADMIN_AUDIT_EXPORT="admin.audit.export"; ADMIN_CHAIN_VERIFY="admin.audit.chain_verify"
    ADMIN_IMPERSONATE="admin.impersonate"; ADMIN_FORCE_LOGOUT="admin.force_logout"
    ADMIN_DB_MIGRATION="admin.db.migration"; ADMIN_CONFIG_CHANGE="admin.config.change"
    TENANT_CREATE="tenant.create"; TENANT_SUSPEND="tenant.suspend"
    TENANT_REACTIVATE="tenant.reactivate"; TENANT_DATA_ACCESS="tenant.data.access"
    TENANT_PURGE="tenant.purge"; TENANT_PLAN_CHANGE="tenant.plan.change"
    DASHBOARD_ACCESS="dashboard.access"; DASHBOARD_EXPORT="dashboard.export"
    DATA_SENSITIVE_ACCESS="data.access.sensitive"; SYSTEM_ERROR="system.error"

EVENT_SEVERITY: Dict[AuditEvent, Severity] = {
    AuditEvent.AUTH_LOGIN_OK: Severity.INFO,
    AuditEvent.AUTH_LOGIN_FAIL: Severity.WARNING,
    AuditEvent.AUTH_LOGIN_LOCKOUT: Severity.CRITICAL,
    AuditEvent.AUTH_LOGOUT: Severity.INFO,
    AuditEvent.AUTH_REGISTER: Severity.INFO,
    AuditEvent.AUTH_TOKEN_REFRESH: Severity.INFO,
    AuditEvent.AUTH_TOKEN_REVOKE: Severity.WARNING,
    AuditEvent.AUTH_TOKEN_REUSE: Severity.CRITICAL,
    AuditEvent.RBAC_PERMISSION_DENIED: Severity.WARNING,
    AuditEvent.RBAC_ROLE_CHANGED: Severity.WARNING,
    AuditEvent.RBAC_ESCALATION_ATTEMPT: Severity.CRITICAL,
    AuditEvent.RBAC_USER_BLOCKED: Severity.WARNING,
    AuditEvent.RBAC_USER_UNBLOCKED: Severity.INFO,
    AuditEvent.RBAC_USER_DELETED: Severity.CRITICAL,
    AuditEvent.LICENSE_ISSUED: Severity.INFO,
    AuditEvent.LICENSE_ACTIVATED: Severity.INFO,
    AuditEvent.LICENSE_EXPIRED: Severity.WARNING,
    AuditEvent.LICENSE_REVOKED: Severity.CRITICAL,
    AuditEvent.LICENSE_SUSPENDED: Severity.WARNING,
    AuditEvent.LICENSE_REACTIVATED: Severity.INFO,
    AuditEvent.LICENSE_DEVICE_ADD: Severity.INFO,
    AuditEvent.LICENSE_DEVICE_REMOVE: Severity.INFO,
    AuditEvent.BILLING_CHECKOUT: Severity.INFO,
    AuditEvent.BILLING_PAYMENT_OK: Severity.INFO,
    AuditEvent.BILLING_PAYMENT_FAIL: Severity.WARNING,
    AuditEvent.BILLING_REFUND: Severity.WARNING,
    AuditEvent.BILLING_PLAN_CHANGED: Severity.INFO,
    AuditEvent.BILLING_SUB_CANCEL: Severity.WARNING,
    AuditEvent.BILLING_WEBHOOK_OK: Severity.INFO,
    AuditEvent.BILLING_WEBHOOK_FAIL: Severity.WARNING,
    AuditEvent.TRADE_OPEN: Severity.INFO,
    AuditEvent.TRADE_CLOSE: Severity.INFO,
    AuditEvent.TRADE_CANCEL: Severity.WARNING,
    AuditEvent.TRADE_DUPLICATE_BLOCKED: Severity.WARNING,
    AuditEvent.SIGNAL_EMIT: Severity.INFO,
    AuditEvent.SIGNAL_DEDUP_BLOCKED: Severity.INFO,
    AuditEvent.SIGNAL_EXPIRE: Severity.INFO,
    AuditEvent.RECON_MISMATCH: Severity.CRITICAL,
    AuditEvent.RISK_DRAWDOWN_ALERT: Severity.WARNING,
    AuditEvent.RISK_DRAWDOWN_CRITICAL: Severity.CRITICAL,
    AuditEvent.RISK_KILL_SWITCH_ON: Severity.CRITICAL,
    AuditEvent.RISK_KILL_SWITCH_OFF: Severity.WARNING,
    AuditEvent.RISK_HALT: Severity.CRITICAL,
    AuditEvent.RISK_RESUME: Severity.WARNING,
    AuditEvent.RISK_LIMIT_BREACH: Severity.WARNING,
    AuditEvent.RISK_HEARTBEAT_LOSS: Severity.CRITICAL,
    AuditEvent.ADMIN_SETTINGS_CHANGED: Severity.WARNING,
    AuditEvent.ADMIN_CROSS_TENANT: Severity.WARNING,
    AuditEvent.ADMIN_AUDIT_EXPORT: Severity.WARNING,
    AuditEvent.ADMIN_CHAIN_VERIFY: Severity.INFO,
    AuditEvent.ADMIN_IMPERSONATE: Severity.CRITICAL,
    AuditEvent.ADMIN_FORCE_LOGOUT: Severity.WARNING,
    AuditEvent.ADMIN_DB_MIGRATION: Severity.WARNING,
    AuditEvent.ADMIN_CONFIG_CHANGE: Severity.WARNING,
    AuditEvent.TENANT_CREATE: Severity.INFO,
    AuditEvent.TENANT_SUSPEND: Severity.CRITICAL,
    AuditEvent.TENANT_REACTIVATE: Severity.INFO,
    AuditEvent.TENANT_DATA_ACCESS: Severity.INFO,
    AuditEvent.TENANT_PURGE: Severity.CRITICAL,
    AuditEvent.TENANT_PLAN_CHANGE: Severity.INFO,
    AuditEvent.DASHBOARD_ACCESS: Severity.INFO,
    AuditEvent.DASHBOARD_EXPORT: Severity.INFO,
    AuditEvent.DATA_SENSITIVE_ACCESS: Severity.WARNING,
    AuditEvent.SYSTEM_ERROR: Severity.CRITICAL,
}

REQUIRES_REASON: frozenset = frozenset({
    AuditEvent.LICENSE_REVOKED, AuditEvent.LICENSE_SUSPENDED,
    AuditEvent.RBAC_ROLE_CHANGED, AuditEvent.RBAC_USER_BLOCKED,
    AuditEvent.RBAC_USER_DELETED, AuditEvent.RISK_HALT,
    AuditEvent.RISK_KILL_SWITCH_ON, AuditEvent.RISK_KILL_SWITCH_OFF,
    AuditEvent.TENANT_SUSPEND, AuditEvent.TENANT_PURGE,
    AuditEvent.ADMIN_IMPERSONATE, AuditEvent.ADMIN_FORCE_LOGOUT,
    AuditEvent.BILLING_REFUND,
})

_DEFAULT_SECRET: bytes = b"audit-chain-secret-CHANGE-IN-PRODUCTION-v21"
MAX_RECORDS: int = 50_000
MAX_AGE_HOURS: int = 720

# EVENT_META: compatibility alias
EVENT_META: Dict[str, Dict] = {
    e.value: {
        "severity": EVENT_SEVERITY.get(e, Severity.INFO).value,
        "requires_reason": e in REQUIRES_REASON,
        "namespace": e.value.split(".")[0],
    }
    for e in AuditEvent
}


@dataclass
class AuditRecord:
    id: str; seq: int; event: str; severity: str; ts: float
    user_id: str; tenant_id: str; actor_id: str; reason: str
    detail: Dict[str, Any]; ip: Optional[str]
    prev_hash: str; chain_hash: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "seq": self.seq, "event": self.event,
            "severity": self.severity, "ts": self.ts,
            "user_id": self.user_id, "tenant_id": self.tenant_id,
            "actor_id": self.actor_id, "reason": self.reason,
            "detail": self.detail, "ip": self.ip,
            "prev_hash": self.prev_hash, "chain_hash": self.chain_hash,
        }


class AuditChain:
    """HMAC-SHA256 tamper-evident hash chain."""

    def __init__(self, secret: bytes | str = _DEFAULT_SECRET) -> None:
        self._secret = secret.encode() if isinstance(secret, str) else secret
        self._lock = threading.RLock()
        self._records: List[AuditRecord] = []
        self._seq: int = 0
        self._hooks: List[Callable[[AuditRecord], None]] = []
        self._db_writer: Optional[Callable] = None
        # genesis is stored as attribute (tests access chain._genesis)
        self._genesis: str = self._recompute_genesis()
        self._prev: str = self._genesis

    def _recompute_genesis(self) -> str:
        return _hmac.new(self._secret, b"GENESIS:AUDIT:CHAIN:V21", hashlib.sha256).hexdigest()

    @staticmethod
    def _canon(rid: str, event: str, ts: float, user_id: str,
               tenant_id: str, reason: str, detail: Dict) -> bytes:
        return json.dumps(
            {"id": rid, "event": event, "ts": f"{ts:.6f}",
             "user_id": user_id, "tenant_id": tenant_id,
             "reason": reason, "detail": detail},
            sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        ).encode()

    def _compute(self, prev: str, rid: str, event: str, ts: float,
                 user_id: str, tenant_id: str, reason: str, detail: Dict) -> str:
        canon = self._canon(rid, event, ts, user_id, tenant_id, reason, detail)
        msg = (prev + ":").encode() + canon
        return _hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def record(
        self,
        event: AuditEvent | str,
        *,
        user_id: str = "",
        tenant_id: str = "default",
        actor_id: Optional[str] = None,
        reason: str = "",
        ip: Any = None,
        detail: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> AuditRecord:
        ev = AuditEvent(event) if isinstance(event, str) else event
        reason = str(reason) if reason is not None else ""
        if ev in REQUIRES_REASON and not reason.strip():
            raise MissingReasonError(f"Event '{ev.value}' requires a reason.")
        det = {**(detail or {}), **kwargs}
        sev = EVENT_SEVERITY.get(ev, Severity.INFO).value
        rid = str(uuid.uuid4())
        ts = time.time()
        aid = actor_id if actor_id is not None else user_id
        with self._lock:
            self._seq += 1  # seq starts at 1
            seq = self._seq
            prev = self._prev
            ch = self._compute(prev, rid, ev.value, ts, user_id, tenant_id, reason, det)
            r = AuditRecord(
                id=rid, seq=seq, event=ev.value, severity=sev, ts=ts,
                user_id=user_id, tenant_id=tenant_id, actor_id=aid,
                reason=reason, detail=det, ip=ip,
                prev_hash=prev, chain_hash=ch,
            )
            self._records.append(r)
            self._prev = ch
            self._evict()
        for hook in list(self._hooks):
            try: hook(r)
            except Exception: pass
        if self._db_writer:
            try: self._db_writer(r)
            except Exception: pass
        return r

    def _evict(self) -> None:
        while len(self._records) > MAX_RECORDS:
            self._records.pop(0)
        cut = time.time() - MAX_AGE_HOURS * 3600
        while self._records and self._records[0].ts < cut:
            self._records.pop(0)

    def add_hook(self, fn: Callable[[AuditRecord], None]) -> None:
        with self._lock:
            self._hooks.append(fn)

    def set_db_writer(self, fn: Callable) -> None:
        with self._lock:
            self._db_writer = fn

    def verify_chain(self) -> bool:
        with self._lock:
            recs = list(self._records)
        if not recs:
            return True
        prev = self._genesis
        for i, r in enumerate(recs):
            ch = self._compute(prev, r.id, r.event, r.ts, r.user_id, r.tenant_id, r.reason, r.detail)
            if not _hmac.compare_digest(r.chain_hash, ch):
                return False
            if i > 0 and r.prev_hash != recs[i-1].chain_hash:
                return False
            prev = r.chain_hash
        return True

    def verify_entry(self, record: AuditRecord) -> bool:
        ch = self._compute(record.prev_hash, record.id, record.event, record.ts,
                           record.user_id, record.tenant_id, record.reason, record.detail)
        return _hmac.compare_digest(record.chain_hash, ch)

    def detect_tampered(self) -> List[int]:
        broken = []
        with self._lock:
            recs = list(self._records)
        prev = self._genesis
        for r in recs:
            ch = self._compute(prev, r.id, r.event, r.ts, r.user_id, r.tenant_id, r.reason, r.detail)
            if not _hmac.compare_digest(r.chain_hash, ch):
                broken.append(r.seq)
            prev = r.chain_hash
        return broken

    def query(self, *, user_id=None, tenant_id=None, event=None,
              severity=None, since_ts=None, until_ts=None, limit=100):
        with self._lock:
            recs = list(self._records)
        out = []
        for r in reversed(recs):  # most-recent first
            if user_id and r.user_id != user_id: continue
            if tenant_id and r.tenant_id != tenant_id: continue
            if event and r.event != event.value: continue
            if severity and r.severity != severity.value: continue
            if since_ts and r.ts < since_ts: continue
            if until_ts and r.ts > until_ts: continue
            out.append(r)
            if len(out) >= limit: break
        return out

    def export_jsonl(self, *, tenant_id=None, since_ts=None) -> str:
        with self._lock:
            recs = list(self._records)
        lines = []
        for r in recs:
            if tenant_id and r.tenant_id != tenant_id: continue
            if since_ts and r.ts < since_ts: continue
            lines.append(json.dumps(r.to_dict(), sort_keys=True))
        return "\n".join(lines)

    def export_csv(self, *, tenant_id=None) -> str:
        with self._lock:
            recs = list(self._records)
        buf = io.StringIO()
        fields = ["seq","id","event","severity","ts","user_id",
                  "tenant_id","actor_id","reason","ip","chain_hash","prev_hash"]
        w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            if tenant_id and r.tenant_id != tenant_id: continue
            row = r.to_dict()
            row["detail"] = json.dumps(row.pop("detail", {}))
            w.writerow({k: row.get(k, "") for k in fields})
        return buf.getvalue()

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            recs = list(self._records)
        g = self._genesis
        crit = sum(1 for r in recs if r.severity == Severity.CRITICAL.value)
        return {
            "total": len(recs),
            "critical_count": crit,
            "last_hash": recs[-1].chain_hash if recs else g,
            "last_seq": recs[-1].seq if recs else 0,
            "seq_max": recs[-1].seq if recs else 0,
            "genesis_hash": g,
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._seq = 0
            self._genesis = self._recompute_genesis()
            self._prev = self._genesis

    @property
    def records(self) -> List[AuditRecord]:
        with self._lock:
            return list(self._records)

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


class AuditLogger:
    """High-level facade with domain-specific convenience methods."""

    def __init__(self, chain: Optional[AuditChain] = None,
                 secret: bytes | str = _DEFAULT_SECRET) -> None:
        self._chain = chain if chain is not None else AuditChain(secret=secret)
        self._hooks: List[Callable] = []

    def add_hook(self, fn: Callable) -> None:
        self._chain.add_hook(fn)

    def add_write_hook(self, fn: Callable) -> None:
        """Alias for add_hook."""
        self._hooks.append(fn)

    def set_db_writer(self, fn: Callable) -> None:
        self._chain.set_db_writer(fn)

    def _record(self, event: AuditEvent, **kw) -> AuditRecord:
        rec = self._chain.record(event, **kw)
        for hook in list(self._hooks):
            try: hook(rec)
            except Exception: pass
        return rec

    def reset(self) -> None:
        self._chain.reset()

    # AUTH
    def auth_login_ok(self, user_id: str = "", tenant_id: str = "default",
                      ip: Any = None, **kw) -> AuditRecord:
        return self._record(AuditEvent.AUTH_LOGIN_OK, user_id=user_id,
                            tenant_id=tenant_id, ip=ip, **kw)

    def auth_login_fail(self, user_id: str = "", tenant_id: str = "default",
                        ip: Any = None, **kw) -> AuditRecord:
        return self._record(AuditEvent.AUTH_LOGIN_FAIL, user_id=user_id,
                            tenant_id=tenant_id, ip=ip, **kw)

    def auth_login_lockout(self, user_id: str = "", tenant_id: str = "default",
                           ip: Any = None, **kw) -> AuditRecord:
        return self._record(AuditEvent.AUTH_LOGIN_LOCKOUT, user_id=user_id,
                            tenant_id=tenant_id, ip=ip, **kw)

    def auth_logout(self, user_id: str = "", tenant_id: str = "default",
                    **kw) -> AuditRecord:
        return self._record(AuditEvent.AUTH_LOGOUT, user_id=user_id,
                            tenant_id=tenant_id, **kw)

    def auth_token_reuse_detected(self, user_id: str = "",
                                   tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.AUTH_TOKEN_REUSE, user_id=user_id,
                            tenant_id=tenant_id, **kw)

    # RBAC
    def rbac_permission_denied(self, user_id: str = "",
                                tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RBAC_PERMISSION_DENIED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def rbac_role_changed(self, user_id: str = "", reason: str = "",
                          tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RBAC_ROLE_CHANGED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def rbac_escalation_attempt(self, user_id: str = "",
                                 tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RBAC_ESCALATION_ATTEMPT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def rbac_user_blocked(self, user_id: str = "", reason: str = "",
                          tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RBAC_USER_BLOCKED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def rbac_user_deleted(self, user_id: str = "", reason: str = "",
                          tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RBAC_USER_DELETED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    # LICENSE
    def license_issued(self, user_id: str = "", tenant_id: str = "default",
                       **kw) -> AuditRecord:
        return self._record(AuditEvent.LICENSE_ISSUED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def license_revoked(self, user_id: str = "", reason: str = "",
                        tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.LICENSE_REVOKED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def license_expired(self, user_id: str = "", tenant_id: str = "default",
                        **kw) -> AuditRecord:
        return self._record(AuditEvent.LICENSE_EXPIRED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def license_suspended(self, user_id: str = "", reason: str = "",
                          tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.LICENSE_SUSPENDED,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def license_device_add(self, user_id: str = "", tenant_id: str = "default",
                           **kw) -> AuditRecord:
        return self._record(AuditEvent.LICENSE_DEVICE_ADD,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def license_device_remove(self, user_id: str = "", tenant_id: str = "default",
                              **kw) -> AuditRecord:
        return self._record(AuditEvent.LICENSE_DEVICE_REMOVE,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    # BILLING
    def billing_checkout(self, user_id: str = "", tenant_id: str = "default",
                         **kw) -> AuditRecord:
        return self._record(AuditEvent.BILLING_CHECKOUT,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_payment_ok(self, user_id: str = "", amount: float = 0.0,
                           currency: str = "USD", payment_id: str = "",
                           tenant_id: str = "default",
                           detail: Optional[Dict] = None, **kw) -> AuditRecord:
        det = {**(detail or {}), "amount": amount, "currency": currency,
               "payment_id": payment_id}
        return self._record(AuditEvent.BILLING_PAYMENT_OK,
                            user_id=user_id, tenant_id=tenant_id, detail=det, **kw)

    def billing_payment_fail(self, user_id: str = "", tenant_id: str = "default",
                             **kw) -> AuditRecord:
        return self._record(AuditEvent.BILLING_PAYMENT_FAIL,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_refund(self, user_id: str = "", reason: str = "",
                       tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.BILLING_REFUND,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def billing_webhook_ok(self, user_id: str = "", tenant_id: str = "default",
                           **kw) -> AuditRecord:
        return self._record(AuditEvent.BILLING_WEBHOOK_OK,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def billing_webhook_fail(self, user_id: str = "", tenant_id: str = "default",
                             **kw) -> AuditRecord:
        return self._record(AuditEvent.BILLING_WEBHOOK_FAIL,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    # TRADING
    def trade_open(self, user_id: str = "", tenant_id: str = "default",
                   **kw) -> AuditRecord:
        return self._record(AuditEvent.TRADE_OPEN,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def trade_close(self, user_id: str = "", tenant_id: str = "default",
                    **kw) -> AuditRecord:
        return self._record(AuditEvent.TRADE_CLOSE,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    def trade_duplicate_blocked(self, user_id: str = "", ticket: str = "",
                                 tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.TRADE_DUPLICATE_BLOCKED,
                            user_id=user_id, tenant_id=tenant_id, ticket=ticket, **kw)

    def signal_emit(self, user_id: str = "", symbol: str = "",
                    direction: str = "", tenant_id: str = "default",
                    detail: Optional[Dict] = None, **kw) -> AuditRecord:
        det = {**(detail or {})}
        if symbol: det["symbol"] = symbol
        if direction: det["direction"] = direction
        return self._record(AuditEvent.SIGNAL_EMIT,
                            user_id=user_id, tenant_id=tenant_id, detail=det, **kw)

    def reconciliation_mismatch(self, user_id: str = "", symbol: str = "",
                                 broker_qty: float = 0, local_qty: float = 0,
                                 tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RECON_MISMATCH,
                            user_id=user_id, tenant_id=tenant_id,
                            symbol=symbol, broker_qty=broker_qty,
                            local_qty=local_qty, **kw)

    # RISK
    def risk_kill_switch_on(self, user_id: str = "", reason: str = "",
                             tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RISK_KILL_SWITCH_ON,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def risk_kill_switch_off(self, user_id: str = "", reason: str = "",
                              tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RISK_KILL_SWITCH_OFF,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def risk_halt(self, user_id: str = "", reason: str = "",
                  tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RISK_HALT,
                            user_id=user_id, tenant_id=tenant_id, reason=reason, **kw)

    def risk_drawdown_alert(self, user_id: str = "", pct: float = 0.0,
                             tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RISK_DRAWDOWN_ALERT,
                            user_id=user_id, tenant_id=tenant_id,
                            drawdown_pct=pct, **kw)

    def risk_drawdown_critical(self, user_id: str = "", pct: float = 0.0,
                                tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RISK_DRAWDOWN_CRITICAL,
                            user_id=user_id, tenant_id=tenant_id,
                            drawdown_pct=pct, **kw)

    def risk_heartbeat_loss(self, device_id: str = "", gap_s: float = 0.0,
                             tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.RISK_HEARTBEAT_LOSS,
                            user_id=device_id, tenant_id=tenant_id,
                            gap_s=gap_s, **kw)

    # ADMIN
    def admin_cross_tenant(self, user_id: str = "", tenant_id: str = "",
                           target_tenant: str = "", action: str = "",
                           resource_id: str = "", **kw) -> AuditRecord:
        return self._record(AuditEvent.ADMIN_CROSS_TENANT,
                            user_id=user_id, tenant_id=tenant_id,
                            target_tenant=target_tenant, action=action,
                            resource_id=resource_id, **kw)

    def admin_audit_export(self, actor_id: str = "", since_ts: Optional[float] = None,
                           **kw) -> AuditRecord:
        return self._record(AuditEvent.ADMIN_AUDIT_EXPORT,
                            user_id=actor_id, since_ts=since_ts, **kw)

    def admin_impersonate(self, actor_id: str = "", target_user: str = "",
                          reason: str = "", **kw) -> AuditRecord:
        return self._record(AuditEvent.ADMIN_IMPERSONATE,
                            user_id=actor_id, target_user=target_user,
                            reason=reason, **kw)

    def admin_chain_verify(self, user_id: str = "", tenant_id: str = "default",
                           actor_id: Optional[str] = None, **kw) -> AuditRecord:
        uid = actor_id or user_id
        return self._record(AuditEvent.ADMIN_CHAIN_VERIFY,
                            user_id=uid, tenant_id=tenant_id, **kw)

    def admin_settings_changed(self, user_id: str = "",
                                tenant_id: str = "default", **kw) -> AuditRecord:
        return self._record(AuditEvent.ADMIN_SETTINGS_CHANGED,
                            user_id=user_id, tenant_id=tenant_id, **kw)

    # TENANT
    def tenant_create(self, tenant_id: str = "", actor_id: str = "",
                      **kw) -> AuditRecord:
        return self._record(AuditEvent.TENANT_CREATE,
                            user_id=actor_id, tenant_id=tenant_id, **kw)

    def tenant_suspend(self, tenant_id: str = "", actor_id: str = "",
                       reason: str = "", **kw) -> AuditRecord:
        return self._record(AuditEvent.TENANT_SUSPEND,
                            user_id=actor_id, tenant_id=tenant_id, reason=reason, **kw)

    def tenant_purge(self, tenant_id: str = "", actor_id: str = "",
                     reason: str = "", **kw) -> AuditRecord:
        return self._record(AuditEvent.TENANT_PURGE,
                            user_id=actor_id, tenant_id=tenant_id, reason=reason, **kw)

    def tenant_reactivate(self, tenant_id: str = "", actor_id: str = "",
                          **kw) -> AuditRecord:
        return self._record(AuditEvent.TENANT_REACTIVATE,
                            user_id=actor_id, tenant_id=tenant_id, **kw)

    # Delegation
    @property
    def chain(self) -> AuditChain:
        return self._chain

    def verify_chain(self) -> bool:
        return self._chain.verify_chain()

    def verify_entry(self, record: AuditRecord) -> bool:
        return self._chain.verify_entry(record)

    def detect_tampered(self) -> List[int]:
        return self._chain.detect_tampered()

    def query(self, **kw):
        return self._chain.query(**kw)

    def export_jsonl(self, **kw) -> str:
        return self._chain.export_jsonl(**kw)

    def export_csv(self, **kw) -> str:
        return self._chain.export_csv(**kw)

    def summary(self) -> Dict[str, Any]:
        return self._chain.summary()

    def __len__(self) -> int:
        return len(self._chain)


# Global singletons
_default_chain = AuditChain()
audit_chain = _default_chain
audit_logger = AuditLogger(_default_chain)
