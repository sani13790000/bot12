from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple


class KeyType(str, Enum):
    JWT_SIGNING      = "jwt_signing"
    JWT_REFRESH      = "jwt_refresh"
    ENCRYPTION_DEK   = "encryption_dek"
    ENCRYPTION_KEK   = "encryption_kek"
    SIGNING_ARTIFACT = "signing_artifact"
    WEBHOOK_HMAC     = "webhook_hmac"
    AUDIT_CHAIN      = "audit_chain"
    API_SECRET       = "api_secret"
    BACKUP_ENCRYPT   = "backup_encrypt"
    TENANT_ISOLATION = "tenant_isolation"


class KeyStatus(str, Enum):
    ACTIVE    = "active"
    GRACE     = "grace"
    REVOKED   = "revoked"
    EXPIRED   = "expired"
    PENDING   = "pending"


class RotationTrigger(str, Enum):
    SCHEDULED   = "scheduled"
    COMPROMISE  = "compromise"
    MANUAL      = "manual"
    POLICY_AGE  = "policy_age"
    POLICY_USE  = "policy_use"
    BOOTSTRAP   = "bootstrap"


class AuditAction(str, Enum):
    CREATED    = "created"
    ACTIVATED  = "activated"
    ROTATED    = "rotated"
    REVOKED    = "revoked"
    ACCESSED   = "accessed"
    EXPIRED    = "expired"
    VERIFIED   = "verified"
    COMPROMISED = "compromised"
    GRACE_START = "grace_start"
    GRACE_END   = "grace_end"
    EXTENDED    = "extended"
    SCHEDULED   = "scheduled"


REQUIRES_REASON = {
    AuditAction.REVOKED,
    AuditAction.COMPROMISED,
    AuditAction.ROTATED,
    AuditAction.EXTENDED,
}


KEY_MATERIAL_SIZES: Dict[str, int] = {
    KeyType.JWT_SIGNING:      64,
    KeyType.JWT_REFRESH:      64,
    KeyType.ENCRYPTION_DEK:   32,
    KeyType.ENCRYPTION_KEK:   32,
    KeyType.SIGNING_ARTIFACT: 64,
    KeyType.WEBHOOK_HMAC:     32,
    KeyType.AUDIT_CHAIN:      32,
    KeyType.API_SECRET:       32,
    KeyType.BACKUP_ENCRYPT:   32,
    KeyType.TENANT_ISOLATION: 32,
}


@dataclass
class RotationPolicy:
    key_type:        str
    max_age_days:    int   = 90
    grace_days:      int   = 14
    max_uses:        int   = 0
    auto_rotate:     bool  = True
    tenant_id:       Optional[str] = None

    @property
    def max_age_seconds(self) -> float:
        return self.max_age_days * 86400.0

    @property
    def grace_seconds(self) -> float:
        return self.grace_days * 86400.0


DEFAULT_POLICIES: Dict[str, RotationPolicy] = {
    KeyType.JWT_SIGNING:      RotationPolicy(KeyType.JWT_SIGNING,      max_age_days=30,  grace_days=7,  max_uses=0),
    KeyType.JWT_REFRESH:      RotationPolicy(KeyType.JWT_REFRESH,      max_age_days=90,  grace_days=14, max_uses=0),
    KeyType.ENCRYPTION_DEK:   RotationPolicy(KeyType.ENCRYPTION_DEK,   max_age_days=365, grace_days=30, max_uses=1_000_000),
    KeyType.ENCRYPTION_KEK:   RotationPolicy(KeyType.ENCRYPTION_KEK,   max_age_days=730, grace_days=60, max_uses=0, auto_rotate=False),
    KeyType.SIGNING_ARTIFACT: RotationPolicy(KeyType.SIGNING_ARTIFACT, max_age_days=365, grace_days=30, max_uses=0),
    KeyType.WEBHOOK_HMAC:     RotationPolicy(KeyType.WEBHOOK_HMAC,     max_age_days=90,  grace_days=14, max_uses=0),
    KeyType.AUDIT_CHAIN:      RotationPolicy(KeyType.AUDIT_CHAIN,      max_age_days=0,   grace_days=0,  max_uses=0, auto_rotate=False),
    KeyType.API_SECRET:       RotationPolicy(KeyType.API_SECRET,       max_age_days=180, grace_days=14, max_uses=0),
    KeyType.BACKUP_ENCRYPT:   RotationPolicy(KeyType.BACKUP_ENCRYPT,   max_age_days=365, grace_days=30, max_uses=0),
    KeyType.TENANT_ISOLATION: RotationPolicy(KeyType.TENANT_ISOLATION, max_age_days=365, grace_days=30, max_uses=0),
}


COMPROMISE_RUNBOOK = [
    "1. Immediately revoke compromised key (set status=REVOKED)",
    "2. Generate emergency replacement key",
    "3. Activate replacement key immediately (skip normal grace)",
    "4. Invalidate all sessions/tokens signed by compromised key",
    "5. Notify security team and affected tenants",
    "6. Rotate all keys that may share entropy source",
    "7. Review audit log for unauthorized access",
    "8. File incident report with timeline",
]


class MissingReasonError(ValueError):
    pass


class KeyNotFoundError(KeyError):
    pass


class KeyRevokedError(RuntimeError):
    pass


class NoActiveKeyError(RuntimeError):
    pass


class RotationError(RuntimeError):
    pass


@dataclass
class KeyVersion:
    key_id:            str
    key_type:          str
    version:           int
    status:            str
    created_at:        float
    activated_at:      Optional[float]  = None
    expires_at:        Optional[float]  = None
    rotated_at:        Optional[float]  = None
    revoked_at:        Optional[float]  = None
    revoke_reason:     Optional[str]    = None
    use_count:         int              = 0
    tenant_id:         Optional[str]    = None
    signature:         str              = ""
    rotation_trigger:  str              = RotationTrigger.BOOTSTRAP
    _raw:              bytes            = field(default_factory=lambda: b"", repr=False)

    def safe_dict(self) -> dict:
        return {
            "key_id":           self.key_id,
            "key_type":         self.key_type,
            "version":          self.version,
            "status":           self.status,
            "created_at":       self.created_at,
            "activated_at":     self.activated_at,
            "expires_at":       self.expires_at,
            "rotated_at":       self.rotated_at,
            "revoked_at":       self.revoked_at,
            "use_count":        self.use_count,
            "tenant_id":        self.tenant_id,
            "signature":        self.signature,
            "rotation_trigger": self.rotation_trigger,
        }

    @property
    def is_usable_for_verify(self) -> bool:
        return self.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)


class SecretAuditChain:
    GENESIS_CONST = "GENESIS:SECRET:CHAIN:V29"

    def __init__(self, secret: bytes | str = b"audit-secret"):
        self._secret = secret.encode() if isinstance(secret, str) else secret
        self._entries: deque = deque(maxlen=10_000)
        self._lock = threading.Lock()
        self._seq = 0
        self._prev_hash = self._genesis()

    def _genesis(self) -> str:
        return hmac.new(self._secret, self.GENESIS_CONST.encode(), hashlib.sha256).hexdigest()

    def _hmac(self, data: str) -> str:
        return hmac.new(self._secret, data.encode(), hashlib.sha256).hexdigest()

    @property
    def genesis_hash(self) -> str:
        return self._genesis()

    def record(self, action: str, key_id: str, key_type: str,
               version: int, actor: str, tenant_id: Optional[str] = None,
               reason: Optional[str] = None, detail: Optional[dict] = None) -> dict:
        if action in {a.value for a in REQUIRES_REASON}:
            if not reason or not reason.strip():
                raise MissingReasonError(f"reason required for action={action}")
        canonical = json.dumps({
            "action": action, "key_id": key_id, "key_type": key_type,
            "version": version, "actor": actor, "tenant_id": tenant_id,
            "reason": reason, "detail": detail or {},
        }, sort_keys=True)
        with self._lock:
            self._seq += 1
            seq = self._seq
            chain_hash = self._hmac(self._prev_hash + ":" + canonical)
            entry = {
                "seq": seq, "action": action, "key_id": key_id, "key_type": key_type,
                "version": version, "actor": actor, "tenant_id": tenant_id,
                "reason": reason, "detail": detail or {}, "ts": time.time(),
                "prev_hash": self._prev_hash, "chain_hash": chain_hash,
            }
            self._prev_hash = chain_hash
            self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return True
        prev = self._genesis()
        for e in entries:
            canonical = json.dumps({
                "action": e["action"], "key_id": e["key_id"], "key_type": e["key_type"],
                "version": e["version"], "actor": e["actor"], "tenant_id": e["tenant_id"],
                "reason": e["reason"], "detail": e["detail"],
            }, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e["chain_hash"]):
                return False
            prev = e["chain_hash"]
        return True

    def detect_tampered(self) -> List[int]:
        with self._lock:
            entries = list(self._entries)
        broken = []
        prev = self._genesis()
        for e in entries:
            canonical = json.dumps({
                "action": e["action"], "key_id": e["key_id"], "key_type": e["key_type"],
                "version": e["version"], "actor": e["actor"], "tenant_id": e["tenant_id"],
                "reason": e["reason"], "detail": e["detail"],
            }, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e["chain_hash"]):
                broken.append(e["seq"])
            prev = e["chain_hash"]
        return broken

    def query(self, key_id: Optional[str] = None, action: Optional[str] = None,
              key_type: Optional[str] = None, limit: int = 100) -> List[dict]:
        with self._lock:
            entries = list(self._entries)
        entries = list(reversed(entries))
        if key_id:
            entries = [e for e in entries if e["key_id"] == key_id]
        if action:
            entries = [e for e in entries if e["action"] == action]
        if key_type:
            entries = [e for e in entries if e["key_type"] == key_type]
        if limit and limit > 0:
            entries = entries[:limit]
        return entries

    @property
    def total(self) -> int:
        with self._lock:
            return self._seq


class KeyStore:
    def __init__(self):
        self._store: Dict[str, KeyVersion] = {}
        self._lock = threading.Lock()

    def add(self, kv: KeyVersion) -> None:
        with self._lock:
            self._store[kv.key_id] = kv

    def get(self, key_id: str) -> KeyVersion:
        with self._lock:
            kv = self._store.get(key_id)
        if kv is None:
            raise KeyNotFoundError(f"key_id={key_id}")
        return kv

    def get_version(self, key_type: str, version: int,
                    tenant_id: Optional[str] = None) -> KeyVersion:
        with self._lock:
            for kv in self._store.values():
                if kv.key_type == key_type and kv.version == version:
                    if tenant_id is None or kv.tenant_id == tenant_id:
                        return kv
        raise KeyNotFoundError(f"type={key_type} v={version}")

    def active_key(self, key_type: str, tenant_id: Optional[str] = None) -> KeyVersion:
        with self._lock:
            candidates = [
                kv for kv in self._store.values()
                if kv.key_type == key_type
                and kv.status == KeyStatus.ACTIVE
                and (tenant_id is None or kv.tenant_id == tenant_id)
            ]
        if not candidates:
            raise NoActiveKeyError(f"type={key_type}")
        return max(candidates, key=lambda k: k.version)

    def usable_keys(self, key_type: str, tenant_id: Optional[str] = None) -> List[KeyVersion]:
        with self._lock:
            return [
                kv for kv in self._store.values()
                if kv.key_type == key_type
                and kv.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)
                and (tenant_id is None or kv.tenant_id == tenant_id)
            ]

    def list_by_type(self, key_type: str) -> List[KeyVersion]:
        with self._lock:
            return [kv for kv in self._store.values() if kv.key_type == key_type]

    def list_all(self, tenant_id: Optional[str] = None,
                 status: Optional[str] = None) -> List[KeyVersion]:
        with self._lock:
            result = list(self._store.values())
        if tenant_id:
            result = [k for k in result if k.tenant_id == tenant_id]
        if status:
            result = [k for k in result if k.status == status]
        return result

    def update_status(self, key_id: str, status: str,
                      revoke_reason: Optional[str] = None) -> None:
        with self._lock:
            kv = self._store.get(key_id)
            if kv is None:
                raise KeyNotFoundError(key_id)
            kv.status = status
            if revoke_reason:
                kv.revoke_reason = revoke_reason
            if status == KeyStatus.REVOKED:
                kv.revoked_at = time.time()

    def increment_use(self, key_id: str) -> int:
        with self._lock:
            kv = self._store.get(key_id)
            if kv:
                kv.use_count += 1
                return kv.use_count
            return 0


def _generate_key_material(key_type: str) -> bytes:
    size = KEY_MATERIAL_SIZES.get(key_type, 32)
    return secrets.token_bytes(size)


def _sign_key(kv: KeyVersion, master_secret: bytes) -> str:
    canonical = json.dumps({
        "key_id":   kv.key_id,
        "key_type": kv.key_type,
        "version":  kv.version,
        "tenant_id": kv.tenant_id,
    }, sort_keys=True)
    return hmac.new(master_secret, canonical.encode(), hashlib.sha256).hexdigest()


def _verify_key_signature(kv: KeyVersion, master_secret: bytes) -> bool:
    expected = _sign_key(kv, master_secret)
    return hmac.compare_digest(expected, kv.signature)


class RotationPolicyEngine:
    def __init__(self, policies: Optional[Dict[str, RotationPolicy]] = None):
        self._policies = copy.deepcopy(policies if policies is not None else DEFAULT_POLICIES)
        self._lock = threading.Lock()

    def get_policy(self, key_type: str,
                   tenant_id: Optional[str] = None) -> RotationPolicy:
        with self._lock:
            tenant_key = f"{key_type}:{tenant_id}" if tenant_id else None
            if tenant_key and tenant_key in self._policies:
                return self._policies[tenant_key]
            return self._policies.get(key_type, RotationPolicy(key_type))

    def set_tenant_policy(self, key_type: str, tenant_id: str,
                          policy: RotationPolicy) -> None:
        with self._lock:
            self._policies[f"{key_type}:{tenant_id}"] = policy

    def needs_rotation(self, kv: KeyVersion,
                       policy: Optional[RotationPolicy] = None) -> bool:
        p = policy or self.get_policy(kv.key_type, kv.tenant_id)
        if not p.auto_rotate:
            return False
        if kv.status != KeyStatus.ACTIVE:
            return False
        if kv.activated_at is None:
            return False
        age = time.time() - kv.activated_at
        if p.max_age_seconds > 0 and age >= p.max_age_seconds:
            return True
        if p.max_uses > 0 and kv.use_count >= p.max_uses:
            return True
        return False

    def grace_expired(self, kv: KeyVersion,
                      policy: Optional[RotationPolicy] = None) -> bool:
        p = policy or self.get_policy(kv.key_type, kv.tenant_id)
        if kv.status != KeyStatus.GRACE:
            return False
        if kv.expires_at is None:
            return False
        return time.time() >= kv.expires_at

    def due_soon(self, kv: KeyVersion, warn_seconds: float = 86400.0,
                 policy: Optional[RotationPolicy] = None) -> bool:
        p = policy or self.get_policy(kv.key_type, kv.tenant_id)
        if kv.status != KeyStatus.ACTIVE or kv.activated_at is None:
            return False
        if p.max_age_seconds <= 0:
            return False
        age = time.time() - kv.activated_at
        return (p.max_age_seconds - age) <= warn_seconds


class KeyLifecycleManager:
    def __init__(self, master_secret: bytes | str = b"master",
                 audit: Optional[SecretAuditChain] = None,
                 policy_engine: Optional[RotationPolicyEngine] = None):
        self._master = master_secret.encode() if isinstance(master_secret, str) else master_secret
        self._store = KeyStore()
        self._audit = audit or SecretAuditChain()
        self._policy = policy_engine or RotationPolicyEngine()
        self._hooks: List[Callable] = []

    def bootstrap(self, key_type: str, actor: str = "system",
                  tenant_id: Optional[str] = None) -> KeyVersion:
        mat = _generate_key_material(key_type)
        kv = KeyVersion(
            key_id=str(uuid.uuid4()), key_type=key_type, version=1,
            status=KeyStatus.ACTIVE, created_at=time.time(),
            activated_at=time.time(), tenant_id=tenant_id,
            rotation_trigger=RotationTrigger.BOOTSTRAP, _raw=mat,
        )
        kv.signature = _sign_key(kv, self._master)
        self._store.add(kv)
        self._audit.record(AuditAction.CREATED, kv.key_id, kv.key_type, kv.version,
                           actor, tenant_id)
        self._audit.record(AuditAction.ACTIVATED, kv.key_id, kv.key_type, kv.version,
                           actor, tenant_id)
        self._run_hooks("bootstrap", kv)
        return kv

    def rotate(self, key_type: str, actor: str, reason: str,
               trigger: str = RotationTrigger.MANUAL,
               tenant_id: Optional[str] = None) -> Tuple[KeyVersion, KeyVersion]:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for rotation")
        try:
            old = self._store.active_key(key_type, tenant_id)
        except NoActiveKeyError:
            old = None
        policy = self._policy.get_policy(key_type, tenant_id)
        new_version = (old.version + 1) if old else 1
        mat = _generate_key_material(key_type)
        new_kv = KeyVersion(
            key_id=str(uuid.uuid4()), key_type=key_type, version=new_version,
            status=KeyStatus.ACTIVE, created_at=time.time(),
            activated_at=time.time(), tenant_id=tenant_id,
            rotation_trigger=trigger, _raw=mat,
        )
        new_kv.signature = _sign_key(new_kv, self._master)
        self._store.add(new_kv)
        if old:
            grace_exp = time.time() + policy.grace_seconds
            self._store.update_status(old.key_id, KeyStatus.GRACE)
            old.expires_at = grace_exp
            old.rotated_at = time.time()
            self._audit.record(AuditAction.GRACE_START, old.key_id, old.key_type,
                               old.version, actor, tenant_id,
                               reason="grace after rotation")
        self._audit.record(AuditAction.ROTATED, new_kv.key_id, new_kv.key_type,
                           new_kv.version, actor, tenant_id, reason=reason)
        self._run_hooks("rotate", new_kv)
        return old, new_kv

    def revoke(self, key_id: str, actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for revoke")
        kv = self._store.get(key_id)
        self._store.update_status(key_id, KeyStatus.REVOKED, revoke_reason=reason)
        self._audit.record(AuditAction.REVOKED, key_id, kv.key_type, kv.version,
                           actor, kv.tenant_id, reason=reason)
        self._run_hooks("revoke", kv)
        return kv

    def access(self, key_type: str, actor: str,
               tenant_id: Optional[str] = None) -> KeyVersion:
        kv = self._store.active_key(key_type, tenant_id)
        if kv.status == KeyStatus.REVOKED:
            raise KeyRevokedError(key_type)
        self._store.increment_use(kv.key_id)
        self._audit.record(AuditAction.ACCESSED, kv.key_id, kv.key_type, kv.version,
                           actor, tenant_id)
        return kv

    def verify_signature(self, kv: KeyVersion) -> bool:
        return _verify_key_signature(kv, self._master)

    def expire_grace_keys(self, actor: str = "scheduler") -> List[str]:
        expired = []
        for kv in self._store.list_all(status=KeyStatus.GRACE):
            if self._policy.grace_expired(kv):
                self._store.update_status(kv.key_id, KeyStatus.EXPIRED)
                self._audit.record(AuditAction.EXPIRED, kv.key_id, kv.key_type,
                                   kv.version, actor, kv.tenant_id,
                                   reason="grace period ended")
                expired.append(kv.key_id)
        return expired

    def add_hook(self, fn: Callable) -> None:
        self._hooks.append(fn)

    def _run_hooks(self, event: str, kv: KeyVersion) -> None:
        for fn in self._hooks:
            try:
                fn(event, kv)
            except Exception:
                pass

    @property
    def store(self) -> KeyStore:
        return self._store

    @property
    def audit(self) -> SecretAuditChain:
        return self._audit

    @property
    def policy(self) -> RotationPolicyEngine:
        return self._policy


class CompromiseResponseManager:
    RUNBOOK = COMPROMISE_RUNBOOK

    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle
        self._reports: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def report_compromise(self, key_id: str, reported_by: str,
                          reason: str) -> dict:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for compromise report")
        kv = self._lc.store.get(key_id)
        self._lc.store.update_status(key_id, KeyStatus.REVOKED, revoke_reason=reason)
        self._lc._audit.record(
            AuditAction.COMPROMISED, key_id, kv.key_type, kv.version,
            reported_by, kv.tenant_id, reason=reason,
        )
        _, new_kv = self._lc.rotate(
            kv.key_type, reported_by,
            reason=f"emergency rotation after compromise: {reason}",
            trigger=RotationTrigger.COMPROMISE,
            tenant_id=kv.tenant_id,
        )
        report = {
            "report_id":   str(uuid.uuid4()),
            "key_id":      key_id,
            "key_type":    kv.key_type,
            "version":     kv.version,
            "reported_by": reported_by,
            "reported_at": time.time(),
            "reason":      reason,
            "new_key_id":  new_kv.key_id,
            "resolved":    False,
            "steps_taken": self.RUNBOOK[:4],
        }
        with self._lock:
            self._reports[report["report_id"]] = report
        return report

    def resolve(self, report_id: str, resolved_by: str) -> dict:
        with self._lock:
            r = self._reports.get(report_id)
            if r is None:
                raise KeyNotFoundError(report_id)
            r["resolved"] = True
            r["resolved_at"] = time.time()
            r["resolved_by"] = resolved_by
            r["steps_taken"] = self.RUNBOOK
        return r

    def open_reports(self) -> List[dict]:
        with self._lock:
            return [r for r in self._reports.values() if not r["resolved"]]

    def all_reports(self) -> List[dict]:
        with self._lock:
            return list(self._reports.values())


class SchedulerAndExtender:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle
        self._scheduled: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def schedule_rotation(self, key_type: str, at_ts: float,
                          actor: str = "scheduler",
                          tenant_id: Optional[str] = None) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._scheduled[job_id] = {
                "job_id": job_id, "key_type": key_type,
                "at_ts": at_ts, "actor": actor,
                "tenant_id": tenant_id, "done": False,
            }
        self._lc._audit.record(
            AuditAction.SCHEDULED, job_id, key_type, 0,
            actor, tenant_id,
        )
        return job_id

    def run_due(self) -> List[str]:
        now = time.time()
        rotated = []
        with self._lock:
            due = [j for j in self._scheduled.values()
                   if not j["done"] and j["at_ts"] <= now]
        for job in due:
            try:
                self._lc.rotate(
                    job["key_type"], job["actor"],
                    reason="scheduled rotation",
                    trigger=RotationTrigger.SCHEDULED,
                    tenant_id=job["tenant_id"],
                )
                with self._lock:
                    self._scheduled[job["job_id"]]["done"] = True
                rotated.append(job["job_id"])
            except Exception:
                pass
        return rotated

    def extend_grace(self, key_id: str, extra_seconds: float,
                     actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for grace extension")
        kv = self._lc.store.get(key_id)
        if kv.status != KeyStatus.GRACE:
            raise RotationError(f"key {key_id} not in GRACE status")
        old_exp = kv.expires_at or time.time()
        kv.expires_at = old_exp + extra_seconds
        self._lc._audit.record(
            AuditAction.EXTENDED, key_id, kv.key_type, kv.version,
            actor, kv.tenant_id, reason=reason,
        )
        return kv

    def pending_jobs(self) -> List[dict]:
        with self._lock:
            return [j for j in self._scheduled.values() if not j["done"]]


class SecretRotationAdmin:
    def __init__(self, master_secret: bytes | str = b"master",
                 audit_secret: bytes | str = b"audit-secret"):
        self._audit = SecretAuditChain(audit_secret)
        self._policy = RotationPolicyEngine()
        self._lifecycle = KeyLifecycleManager(
            master_secret=master_secret,
            audit=self._audit,
            policy_engine=self._policy,
        )
        self._compromise = CompromiseResponseManager(self._lifecycle)
        self._scheduler = SchedulerAndExtender(self._lifecycle)

    def bootstrap_all(self, actor: str = "system",
                      tenant_id: Optional[str] = None) -> Dict[str, KeyVersion]:
        result = {}
        for kt in KeyType:
            try:
                kv = self._lifecycle.bootstrap(kt.value, actor, tenant_id)
                result[kt.value] = kv
            except Exception:
                pass
        return result

    def rotate_key(self, key_type: str, actor: str, reason: str,
                   tenant_id: Optional[str] = None) -> Tuple[Optional[KeyVersion], KeyVersion]:
        return self._lifecycle.rotate(key_type, actor, reason, tenant_id=tenant_id)

    def revoke_key(self, key_id: str, actor: str, reason: str) -> KeyVersion:
        return self._lifecycle.revoke(key_id, actor, reason)

    def report_compromise(self, key_id: str, reported_by: str,
                          reason: str) -> dict:
        return self._compromise.report_compromise(key_id, reported_by, reason)

    def summary(self, tenant_id: Optional[str] = None) -> dict:
        all_keys = self._lifecycle.store.list_all(tenant_id=tenant_id)
        by_type: Dict[str, dict] = {}
        for kv in all_keys:
            t = kv.key_type
            if t not in by_type:
                by_type[t] = {"active": 0, "grace": 0, "revoked": 0, "expired": 0, "pending": 0}
            by_type[t][kv.status] = by_type[t].get(kv.status, 0) + 1
        return {
            "total_keys":    len(all_keys),
            "by_type":       by_type,
            "open_compromises": len(self._compromise.open_reports()),
            "audit_total":   self._audit.total,
            "chain_valid":   self._audit.verify_chain(),
        }

    def verify_audit_chain(self) -> bool:
        return self._audit.verify_chain()

    def get_runbook(self) -> List[str]:
        return CompromiseResponseManager.RUNBOOK

    @property
    def lifecycle(self) -> KeyLifecycleManager:
        return self._lifecycle

    @property
    def audit(self) -> SecretAuditChain:
        return self._audit

    @property
    def compromise(self) -> CompromiseResponseManager:
        return self._compromise

    @property
    def scheduler(self) -> SchedulerAndExtender:
        return self._scheduler


def build_secret_rotation(master_secret: bytes | str = b"master",
                          audit_secret: bytes | str = b"audit-secret") -> SecretRotationAdmin:
    return SecretRotationAdmin(master_secret=master_secret, audit_secret=audit_secret)


__all__ = [
    "KeyType", "KeyStatus", "RotationTrigger", "AuditAction",
    "REQUIRES_REASON", "KEY_MATERIAL_SIZES", "DEFAULT_POLICIES", "COMPROMISE_RUNBOOK",
    "RotationPolicy", "KeyVersion", "SecretAuditChain", "KeyStore",
    "RotationPolicyEngine", "KeyLifecycleManager", "CompromiseResponseManager",
    "SchedulerAndExtender", "SecretRotationAdmin", "build_secret_rotation",
    "MissingReasonError", "KeyNotFoundError", "KeyRevokedError",
    "NoActiveKeyError", "RotationError",
]