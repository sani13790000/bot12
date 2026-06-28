"""
backend/core/secret_rotation.py
Galaxy Vast AI -- Phase 29: Secure Secrets Rotation & Key Lifecycle

P29-1: rotation policy for JWT/encryption/signing/webhook keys
P29-2: key versioning with grace period (old key still verifies during overlap)
P29-3: tamper-evident audit chain for every secret access / rotation
P29-4: compromise response plan (immediate revoke + emergency rotation)
P29-5: zero-downtime rotation (new key encrypts, old key still decrypts)
P29-6: HMAC-SHA256 key signatures -- keys are self-authenticating
P29-7: no plaintext secrets in logs, repr, or exceptions
"""
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


# ---------------------------------------------------------------------------
# Enums & Constants
# ---------------------------------------------------------------------------

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
    KEY_GENERATED  = "key.generated"
    KEY_ACTIVATED  = "key.activated"
    KEY_ROTATED    = "key.rotated"
    KEY_REVOKED    = "key.revoked"
    KEY_EXPIRED    = "key.expired"
    KEY_ACCESSED   = "key.accessed"
    KEY_VERIFIED   = "key.verified"
    COMPROMISE_ACK = "key.compromise_ack"
    GRACE_EXTENDED = "key.grace_extended"
    POLICY_UPDATED = "key.policy_updated"
    EMERGENCY_ROT  = "key.emergency_rotation"


REQUIRES_REASON = {
    AuditAction.KEY_REVOKED,
    AuditAction.COMPROMISE_ACK,
    AuditAction.EMERGENCY_ROT,
    AuditAction.KEY_EXPIRED,
}

_POLICY_DEFAULTS: Dict[KeyType, Dict] = {
    KeyType.JWT_SIGNING:      dict(max_age_days=30,  grace_days=7,  max_uses=0,        auto_rotate=True),
    KeyType.JWT_REFRESH:      dict(max_age_days=90,  grace_days=14, max_uses=0,        auto_rotate=True),
    KeyType.ENCRYPTION_DEK:   dict(max_age_days=90,  grace_days=30, max_uses=1_000_000, auto_rotate=True),
    KeyType.ENCRYPTION_KEK:   dict(max_age_days=365, grace_days=60, max_uses=0,        auto_rotate=False),
    KeyType.SIGNING_ARTIFACT: dict(max_age_days=180, grace_days=30, max_uses=0,        auto_rotate=True),
    KeyType.WEBHOOK_HMAC:     dict(max_age_days=60,  grace_days=14, max_uses=0,        auto_rotate=True),
    KeyType.AUDIT_CHAIN:      dict(max_age_days=365, grace_days=90, max_uses=0,        auto_rotate=False),
    KeyType.API_SECRET:       dict(max_age_days=90,  grace_days=7,  max_uses=0,        auto_rotate=True),
    KeyType.BACKUP_ENCRYPT:   dict(max_age_days=365, grace_days=60, max_uses=0,        auto_rotate=False),
    KeyType.TENANT_ISOLATION: dict(max_age_days=180, grace_days=30, max_uses=0,        auto_rotate=True),
}

COMPROMISE_RUNBOOK: List[str] = [
    "STEP-1: Immediately revoke compromised key (status=REVOKED)",
    "STEP-2: Generate emergency replacement key",
    "STEP-3: Activate new key (zero-downtime cutover)",
    "STEP-4: Reject all tokens/signatures from revoked key",
    "STEP-5: Notify security team via P1 alert",
    "STEP-6: Audit all recent accesses of compromised key",
    "STEP-7: Rotate all derived/dependent keys",
    "STEP-8: Verify new key works end-to-end",
    "STEP-9: Update key registry and downstream configs",
    "STEP-10: Post-mortem: root cause + timeline + remediation",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SecretRotationError(Exception): pass
class KeyNotFoundError(SecretRotationError): pass
class KeyRevokedError(SecretRotationError): pass
class KeyExpiredError(SecretRotationError): pass
class MissingReasonError(SecretRotationError): pass
class PolicyViolationError(SecretRotationError): pass
class CompromiseResponseError(SecretRotationError): pass


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class RotationPolicy:
    key_type:      KeyType
    max_age_days:  int   = 90
    grace_days:    int   = 14
    max_uses:      int   = 0
    auto_rotate:   bool  = True
    tenant_id:     Optional[str] = None

    @classmethod
    def default_for(cls, key_type: KeyType,
                    tenant_id: Optional[str] = None) -> "RotationPolicy":
        d = _POLICY_DEFAULTS.get(key_type, {})
        return cls(key_type=key_type, tenant_id=tenant_id, **d)

    @property
    def max_age_seconds(self) -> float:
        return self.max_age_days * 86400.0

    @property
    def grace_seconds(self) -> float:
        return self.grace_days * 86400.0


@dataclass
class KeyVersion:
    key_id:        str
    key_type:      KeyType
    version:       int
    status:        KeyStatus
    created_at:    float
    activated_at:  Optional[float]
    expires_at:    Optional[float]
    rotated_at:    Optional[float]
    revoked_at:    Optional[float]
    use_count:     int
    tenant_id:     Optional[str]
    _raw:          bytes = field(repr=False, compare=False)
    signature:     str   = ""
    rotation_trigger: RotationTrigger = RotationTrigger.BOOTSTRAP
    revoke_reason: Optional[str] = None

    def safe_dict(self) -> dict:
        return {
            "key_id":           self.key_id,
            "key_type":         self.key_type.value,
            "version":          self.version,
            "status":           self.status.value,
            "created_at":       self.created_at,
            "activated_at":     self.activated_at,
            "expires_at":       self.expires_at,
            "rotated_at":       self.rotated_at,
            "revoked_at":       self.revoked_at,
            "use_count":        self.use_count,
            "tenant_id":        self.tenant_id,
            "signature":        self.signature,
            "rotation_trigger": self.rotation_trigger.value,
            "revoke_reason":    self.revoke_reason,
        }

    def is_usable_for_new(self) -> bool:
        return self.status == KeyStatus.ACTIVE

    def is_usable_for_verify(self) -> bool:
        return self.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)


@dataclass
class AuditEntry:
    entry_id:   str
    seq:        int
    action:     AuditAction
    key_id:     str
    key_type:   KeyType
    version:    int
    actor:      str
    tenant_id:  Optional[str]
    reason:     Optional[str]
    detail:     dict
    ts:         float
    prev_hash:  str
    chain_hash: str


@dataclass
class CompromiseReport:
    report_id:      str
    key_id:         str
    key_type:       KeyType
    version:        int
    reported_by:    str
    reported_at:    float
    reason:         str
    new_key_id:     Optional[str]
    steps_taken:    List[str]
    resolved:       bool = False
    resolved_at:    Optional[float] = None


# ---------------------------------------------------------------------------
# HMAC Audit Chain
# ---------------------------------------------------------------------------

_GENESIS_CONST = b"GENESIS:SECRET:ROTATION:V29"


class SecretAuditChain:
    def __init__(self, secret: bytes | str = b""):
        if isinstance(secret, str):
            secret = secret.encode()
        self._secret = secret or os.urandom(32)
        self._entries: deque[AuditEntry] = deque()
        self._lock = threading.RLock()
        self._seq = 1
        self._prev_hash = self._genesis_hash()

    def _genesis_hash(self) -> str:
        return hmac.new(self._secret, _GENESIS_CONST,
                        digestmod=hashlib.sha256).hexdigest()

    def _hmac(self, prev_hash: str, canonical: str) -> str:
        msg = f"{prev_hash}:{canonical}".encode()
        return hmac.new(self._secret, msg,
                        digestmod=hashlib.sha256).hexdigest()

    def record(self, action: AuditAction, key_id: str, key_type: KeyType,
               version: int, actor: str, reason: Optional[str] = None,
               tenant_id: Optional[str] = None, **detail) -> AuditEntry:
        if action in REQUIRES_REASON:
            if not reason or not reason.strip():
                raise MissingReasonError(
                    f"reason is mandatory for action={action.value}")
        with self._lock:
            ts_now = time.time()
            canonical = json.dumps({
                "action":    action.value,
                "key_id":    key_id,
                "key_type":  key_type.value,
                "version":   version,
                "actor":     actor,
                "tenant_id": tenant_id,
                "reason":    reason,
                "detail":    detail,
                "ts":        ts_now,
            }, sort_keys=True)
            chain_hash = self._hmac(self._prev_hash, canonical)
            entry = AuditEntry(
                entry_id=str(uuid.uuid4()),
                seq=self._seq,
                action=action,
                key_id=key_id,
                key_type=key_type,
                version=version,
                actor=actor,
                tenant_id=tenant_id,
                reason=reason,
                detail=detail,
                ts=ts_now,
                prev_hash=self._prev_hash,
                chain_hash=chain_hash,
            )
            self._entries.append(entry)
            self._prev_hash = chain_hash
            self._seq += 1
        return entry

    def verify_chain(self) -> bool:
        with self._lock:
            entries = list(self._entries)
        if not entries:
            return True
        prev = self._genesis_hash()
        for e in entries:
            canonical = json.dumps({
                "action":    e.action.value,
                "key_id":    e.key_id,
                "key_type":  e.key_type.value,
                "version":   e.version,
                "actor":     e.actor,
                "tenant_id": e.tenant_id,
                "reason":    e.reason,
                "detail":    e.detail,
                "ts":        e.ts,
            }, sort_keys=True)
            expected = self._hmac(prev, canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                return False
            prev = e.chain_hash
        return True

    def detect_tampered(self) -> List[int]:
        with self._lock:
            entries = list(self._entries)
        broken = []
        if not entries:
            return broken
        prev = self._genesis_hash()
        for e in entries:
            canonical = json.dumps({
                "action":    e.action.value,
                "key_id":    e.key_id,
                "key_type":  e.key_type.value,
                "version":   e.version,
                "actor":     e.actor,
                "tenant_id": e.tenant_id,
                "reason":    e.reason,
                "detail":    e.detail,
                "ts":        e.ts,
            }, sort_keys=True)
            expected = self._hmac(prev, canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                broken.append(e.seq)
            prev = e.chain_hash
        return broken

    def query(self, key_id: Optional[str] = None,
              action: Optional[AuditAction] = None,
              actor: Optional[str] = None,
              tenant_id: Optional[str] = None,
              limit: int = 100) -> List[AuditEntry]:
        with self._lock:
            entries = list(self._entries)
        results = list(reversed(entries))
        if key_id:
            results = [e for e in results if e.key_id == key_id]
        if action:
            results = [e for e in results if e.action == action]
        if actor:
            results = [e for e in results if e.actor == actor]
        if tenant_id:
            results = [e for e in results if e.tenant_id == tenant_id]
        if limit > 0:
            results = results[:limit]
        return results

    @property
    def total(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Key Material Generator
# ---------------------------------------------------------------------------

class KeyMaterialGenerator:
    _SIZES: Dict[KeyType, int] = {
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

    @classmethod
    def generate(cls, key_type: KeyType) -> bytes:
        size = cls._SIZES.get(key_type, 32)
        return secrets.token_bytes(size)

    @classmethod
    def key_id(cls) -> str:
        return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Key Self-Authentication
# ---------------------------------------------------------------------------

class KeySelfAuth:
    @staticmethod
    def sign(kv: KeyVersion, master_secret: bytes) -> str:
        canonical = json.dumps({
            "key_id":    kv.key_id,
            "key_type":  kv.key_type.value,
            "version":   kv.version,
            "created_at": kv.created_at,
            "tenant_id": kv.tenant_id,
        }, sort_keys=True)
        return hmac.new(master_secret, canonical.encode(),
                        digestmod=hashlib.sha256).hexdigest()

    @staticmethod
    def verify(kv: KeyVersion, master_secret: bytes) -> bool:
        expected = KeySelfAuth.sign(kv, master_secret)
        return hmac.compare_digest(expected, kv.signature)


# ---------------------------------------------------------------------------
# Key Store
# ---------------------------------------------------------------------------

class KeyStore:
    def __init__(self):
        self._keys: Dict[str, List[KeyVersion]] = {}
        self._lock = threading.RLock()

    def add(self, kv: KeyVersion) -> None:
        with self._lock:
            if kv.key_id not in self._keys:
                self._keys[kv.key_id] = []
            self._keys[kv.key_id].append(kv)

    def get(self, key_id: str, version: Optional[int] = None) -> KeyVersion:
        with self._lock:
            versions = self._keys.get(key_id)
            if not versions:
                raise KeyNotFoundError(f"key_id={key_id} not found")
            if version is None:
                kv = versions[-1]
            else:
                found = [v for v in versions if v.version == version]
                if not found:
                    raise KeyNotFoundError(
                        f"key_id={key_id} version={version} not found")
                kv = found[0]
        return kv

    def list_by_type(self, key_type: KeyType,
                     tenant_id: Optional[str] = None,
                     status: Optional[KeyStatus] = None) -> List[KeyVersion]:
        with self._lock:
            all_kvs = [v for vs in self._keys.values() for v in vs]
        result = [k for k in all_kvs if k.key_type == key_type]
        if tenant_id is not None:
            result = [k for k in result if k.tenant_id == tenant_id]
        if status is not None:
            result = [k for k in result if k.status == status]
        return sorted(result, key=lambda k: k.version)

    def active_key(self, key_type: KeyType,
                   tenant_id: Optional[str] = None) -> KeyVersion:
        active = self.list_by_type(key_type, tenant_id=tenant_id,
                                   status=KeyStatus.ACTIVE)
        if not active:
            raise KeyNotFoundError(
                f"No ACTIVE key for type={key_type.value} tenant={tenant_id}")
        return active[-1]

    def usable_keys(self, key_type: KeyType,
                    tenant_id: Optional[str] = None) -> List[KeyVersion]:
        with self._lock:
            all_kvs = [v for vs in self._keys.values() for v in vs]
        return [k for k in all_kvs
                if k.key_type == key_type
                and (tenant_id is None or k.tenant_id == tenant_id)
                and k.is_usable_for_verify()]

    def update_status(self, key_id: str, version: int,
                      status: KeyStatus, **kwargs) -> KeyVersion:
        with self._lock:
            versions = self._keys.get(key_id, [])
            for kv in versions:
                if kv.version == version:
                    kv.status = status
                    for k, v in kwargs.items():
                        setattr(kv, k, v)
                    return kv
        raise KeyNotFoundError(f"key_id={key_id} version={version}")

    def increment_use(self, key_id: str, version: int) -> int:
        with self._lock:
            for kv in self._keys.get(key_id, []):
                if kv.version == version:
                    kv.use_count += 1
                    return kv.use_count
        return 0

    def all_keys(self) -> List[KeyVersion]:
        with self._lock:
            return [v for vs in self._keys.values() for v in vs]


# ---------------------------------------------------------------------------
# Rotation Policy Engine
# ---------------------------------------------------------------------------

class RotationPolicyEngine:
    def __init__(self):
        self._policies: Dict[Tuple[KeyType, Optional[str]], RotationPolicy] = {}
        self._lock = threading.RLock()

    def set_policy(self, policy: RotationPolicy) -> None:
        with self._lock:
            self._policies[(policy.key_type, policy.tenant_id)] = policy

    def get_policy(self, key_type: KeyType,
                   tenant_id: Optional[str] = None) -> RotationPolicy:
        with self._lock:
            p = self._policies.get((key_type, tenant_id))
            if p is None:
                p = self._policies.get((key_type, None))
            if p is None:
                p = RotationPolicy.default_for(key_type, tenant_id)
        return p

    def needs_rotation(self, kv: KeyVersion,
                       now: Optional[float] = None) -> Tuple[bool, str]:
        now = now or time.time()
        policy = self.get_policy(kv.key_type, kv.tenant_id)
        age = now - (kv.activated_at or kv.created_at)
        if age >= policy.max_age_seconds:
            return True, f"max_age_days={policy.max_age_days} exceeded"
        if policy.max_uses > 0 and kv.use_count >= policy.max_uses:
            return True, f"max_uses={policy.max_uses} exceeded"
        return False, ""

    def is_grace_expired(self, kv: KeyVersion,
                         now: Optional[float] = None) -> bool:
        now = now or time.time()
        if kv.expires_at is None:
            return False
        return now >= kv.expires_at

    def due_soon(self, kv: KeyVersion,
                 warn_days: int = 7,
                 now: Optional[float] = None) -> bool:
        now = now or time.time()
        policy = self.get_policy(kv.key_type, kv.tenant_id)
        age = now - (kv.activated_at or kv.created_at)
        remaining = policy.max_age_seconds - age
        return 0 < remaining <= warn_days * 86400.0


# ---------------------------------------------------------------------------
# Key Lifecycle Manager
# ---------------------------------------------------------------------------

class KeyLifecycleManager:
    """
    Zero-downtime rotation:
      1. old ACTIVE -> GRACE  (still valid for verify/decrypt)
      2. new key generated + activated  (used for new sign/encrypt)
    """

    def __init__(self, master_secret: Optional[bytes] = None,
                 audit: Optional[SecretAuditChain] = None):
        self._master = master_secret or os.urandom(32)
        self._store = KeyStore()
        self._policy_engine = RotationPolicyEngine()
        self._audit = audit if audit is not None else SecretAuditChain()
        self._hooks: List[Callable] = []
        self._lock = threading.RLock()
        self._version_counters: Dict[Tuple[KeyType, Optional[str]], int] = {}

    def set_policy(self, policy: RotationPolicy) -> None:
        self._policy_engine.set_policy(policy)
        self._audit.record(
            AuditAction.POLICY_UPDATED, "system",
            policy.key_type, 0, "system",
            tenant_id=policy.tenant_id)

    def get_policy(self, key_type: KeyType,
                   tenant_id: Optional[str] = None) -> RotationPolicy:
        return self._policy_engine.get_policy(key_type, tenant_id)

    def add_rotation_hook(self, fn: Callable) -> None:
        with self._lock:
            self._hooks.append(fn)

    def _fire_hooks(self, event: str, kv: KeyVersion) -> None:
        for fn in list(self._hooks):
            try:
                fn(event, kv)
            except Exception:
                pass

    def _next_version(self, key_type: KeyType,
                      tenant_id: Optional[str]) -> int:
        with self._lock:
            k = (key_type, tenant_id)
            self._version_counters[k] = self._version_counters.get(k, 0) + 1
            return self._version_counters[k]

    def generate_key(self, key_type: KeyType, actor: str = "system",
                     tenant_id: Optional[str] = None,
                     trigger: RotationTrigger = RotationTrigger.BOOTSTRAP,
                     activate: bool = False) -> KeyVersion:
        version = self._next_version(key_type, tenant_id)
        raw = KeyMaterialGenerator.generate(key_type)
        now = time.time()
        kv = KeyVersion(
            key_id=KeyMaterialGenerator.key_id(),
            key_type=key_type, version=version,
            status=KeyStatus.PENDING, created_at=now,
            activated_at=None, expires_at=None,
            rotated_at=None, revoked_at=None, use_count=0,
            tenant_id=tenant_id, _raw=raw, signature="",
            rotation_trigger=trigger,
        )
        kv.signature = KeySelfAuth.sign(kv, self._master)
        self._store.add(kv)
        self._audit.record(
            AuditAction.KEY_GENERATED, kv.key_id, key_type,
            version, actor, tenant_id=tenant_id, trigger=trigger.value)
        self._fire_hooks("generated", kv)
        if activate:
            self.activate_key(kv.key_id, version, actor=actor)
        return self._store.get(kv.key_id, version)

    def activate_key(self, key_id: str, version: int,
                     actor: str = "system") -> KeyVersion:
        kv = self._store.get(key_id, version)
        if kv.status not in (KeyStatus.PENDING,):
            raise PolicyViolationError(
                f"Can only activate PENDING keys, got status={kv.status}")
        kv = self._store.update_status(
            key_id, version, KeyStatus.ACTIVE, activated_at=time.time())
        self._audit.record(
            AuditAction.KEY_ACTIVATED, key_id, kv.key_type,
            version, actor, tenant_id=kv.tenant_id)
        self._fire_hooks("activated", kv)
        return kv

    def rotate_key(self, key_type: KeyType, actor: str = "system",
                   tenant_id: Optional[str] = None,
                   trigger: RotationTrigger = RotationTrigger.SCHEDULED,
                   reason: Optional[str] = None) -> Tuple[KeyVersion, KeyVersion]:
        policy = self._policy_engine.get_policy(key_type, tenant_id)
        now = time.time()
        try:
            old_kv = self._store.active_key(key_type, tenant_id)
        except KeyNotFoundError:
            old_kv = None
        if old_kv is not None:
            expires_at = now + policy.grace_seconds
            old_kv = self._store.update_status(
                old_kv.key_id, old_kv.version, KeyStatus.GRACE,
                rotated_at=now, expires_at=expires_at)
            self._audit.record(
                AuditAction.KEY_ROTATED, old_kv.key_id, key_type,
                old_kv.version, actor, tenant_id=tenant_id,
                trigger=trigger.value, reason=reason, expires_at=expires_at)
            self._fire_hooks("rotated_to_grace", old_kv)
        new_kv = self.generate_key(
            key_type, actor=actor, tenant_id=tenant_id,
            trigger=trigger, activate=True)
        return old_kv, new_kv

    def revoke_key(self, key_id: str, version: int,
                   actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory for revocation")
        kv = self._store.get(key_id, version)
        if kv.status == KeyStatus.REVOKED:
            return kv
        kv = self._store.update_status(
            key_id, version, KeyStatus.REVOKED,
            revoked_at=time.time(), revoke_reason=reason)
        self._audit.record(
            AuditAction.KEY_REVOKED, key_id, kv.key_type,
            version, actor, reason=reason, tenant_id=kv.tenant_id)
        self._fire_hooks("revoked", kv)
        return kv

    def expire_grace_keys(self, actor: str = "system",
                          now: Optional[float] = None,
                          reason: str = "grace period elapsed") -> List[KeyVersion]:
        now = now or time.time()
        expired = []
        for kv in self._store.all_keys():
            if kv.status == KeyStatus.GRACE:
                if self._policy_engine.is_grace_expired(kv, now):
                    self._store.update_status(kv.key_id, kv.version,
                                             KeyStatus.EXPIRED)
                    self._audit.record(
                        AuditAction.KEY_EXPIRED, kv.key_id, kv.key_type,
                        kv.version, actor, reason=reason,
                        tenant_id=kv.tenant_id)
                    expired.append(self._store.get(kv.key_id, kv.version))
                    self._fire_hooks("expired", kv)
        return expired

    def record_access(self, key_id: str, version: int,
                      actor: str = "system") -> int:
        kv = self._store.get(key_id, version)
        if kv.status == KeyStatus.REVOKED:
            self._audit.record(
                AuditAction.KEY_ACCESSED, key_id, kv.key_type,
                version, actor, tenant_id=kv.tenant_id,
                detail="REVOKED key access attempt")
            raise KeyRevokedError(f"key_id={key_id} v{version} is REVOKED")
        if kv.status == KeyStatus.EXPIRED:
            self._audit.record(
                AuditAction.KEY_ACCESSED, key_id, kv.key_type,
                version, actor, tenant_id=kv.tenant_id,
                detail="EXPIRED key access attempt")
            raise KeyExpiredError(f"key_id={key_id} v{version} is EXPIRED")
        count = self._store.increment_use(key_id, version)
        self._audit.record(
            AuditAction.KEY_ACCESSED, key_id, kv.key_type,
            version, actor, tenant_id=kv.tenant_id, use_count=count)
        return count

    def sign_payload(self, payload: bytes, key_type: KeyType,
                     actor: str = "system",
                     tenant_id: Optional[str] = None) -> Tuple[str, str, int]:
        kv = self._store.active_key(key_type, tenant_id)
        self.record_access(kv.key_id, kv.version, actor)
        sig = hmac.new(kv._raw, payload,
                       digestmod=hashlib.sha256).hexdigest()
        return sig, kv.key_id, kv.version

    def verify_payload(self, payload: bytes, signature: str,
                       key_id: str, version: int,
                       actor: str = "system") -> bool:
        kv = self._store.get(key_id, version)
        if not kv.is_usable_for_verify():
            self._audit.record(
                AuditAction.KEY_VERIFIED, key_id, kv.key_type,
                version, actor, tenant_id=kv.tenant_id,
                result="REJECTED", status=kv.status.value)
            return False
        expected = hmac.new(kv._raw, payload,
                            digestmod=hashlib.sha256).hexdigest()
        ok = hmac.compare_digest(expected, signature)
        self._audit.record(
            AuditAction.KEY_VERIFIED, key_id, kv.key_type,
            version, actor, tenant_id=kv.tenant_id,
            result="OK" if ok else "FAIL")
        return ok

    def get_key(self, key_id: str,
                version: Optional[int] = None) -> KeyVersion:
        return self._store.get(key_id, version)

    def list_by_type(self, key_type: KeyType,
                     tenant_id: Optional[str] = None,
                     status: Optional[KeyStatus] = None) -> List[KeyVersion]:
        return self._store.list_by_type(key_type, tenant_id, status)

    def active_key(self, key_type: KeyType,
                   tenant_id: Optional[str] = None) -> KeyVersion:
        return self._store.active_key(key_type, tenant_id)

    def usable_keys(self, key_type: KeyType,
                    tenant_id: Optional[str] = None) -> List[KeyVersion]:
        return self._store.usable_keys(key_type, tenant_id)

    def needs_rotation(self, key_id: str,
                       version: int) -> Tuple[bool, str]:
        kv = self._store.get(key_id, version)
        return self._policy_engine.needs_rotation(kv)

    def due_soon(self, key_id: str, version: int,
                 warn_days: int = 7) -> bool:
        kv = self._store.get(key_id, version)
        return self._policy_engine.due_soon(kv, warn_days)

    def self_auth_valid(self, key_id: str, version: int) -> bool:
        kv = self._store.get(key_id, version)
        return KeySelfAuth.verify(kv, self._master)


# ---------------------------------------------------------------------------
# Compromise Response Manager
# ---------------------------------------------------------------------------

class CompromiseResponseManager:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lifecycle = lifecycle
        self._reports: Dict[str, CompromiseReport] = {}
        self._lock = threading.RLock()

    def report_compromise(self, key_id: str, version: int,
                          reported_by: str, reason: str) -> CompromiseReport:
        if not reason or not reason.strip():
            raise MissingReasonError("reason is mandatory for compromise report")
        kv = self._lifecycle.get_key(key_id, version)
        report_id = str(uuid.uuid4())
        steps: List[str] = []
        self._lifecycle.revoke_key(
            key_id, version, actor=reported_by, reason=reason)
        steps.append(COMPROMISE_RUNBOOK[0])
        self._lifecycle._audit.record(
            AuditAction.EMERGENCY_ROT, key_id, kv.key_type,
            version, reported_by,
            reason=f"compromise: {reason}", tenant_id=kv.tenant_id)
        _, new_kv = self._lifecycle.rotate_key(
            kv.key_type, actor=reported_by, tenant_id=kv.tenant_id,
            trigger=RotationTrigger.COMPROMISE, reason=reason)
        steps.append(COMPROMISE_RUNBOOK[1])
        steps.append(COMPROMISE_RUNBOOK[2])
        self._lifecycle._audit.record(
            AuditAction.COMPROMISE_ACK, key_id, kv.key_type,
            version, reported_by, reason=reason,
            new_key_id=new_kv.key_id, tenant_id=kv.tenant_id)
        steps.append(COMPROMISE_RUNBOOK[3])
        steps.extend(COMPROMISE_RUNBOOK[4:])
        report = CompromiseReport(
            report_id=report_id, key_id=key_id,
            key_type=kv.key_type, version=version,
            reported_by=reported_by, reported_at=time.time(),
            reason=reason, new_key_id=new_kv.key_id, steps_taken=steps)
        with self._lock:
            self._reports[report_id] = report
        return report

    def resolve_report(self, report_id: str,
                       resolved_by: str) -> CompromiseReport:
        with self._lock:
            report = self._reports.get(report_id)
        if not report:
            raise CompromiseResponseError(
                f"report_id={report_id} not found")
        report.resolved = True
        report.resolved_at = time.time()
        self._lifecycle._audit.record(
            AuditAction.KEY_ACCESSED, report.key_id, report.key_type,
            report.version, resolved_by, tenant_id=None,
            detail="compromise report resolved")
        return report

    def list_reports(self,
                     resolved: Optional[bool] = None) -> List[CompromiseReport]:
        with self._lock:
            reports = list(self._reports.values())
        if resolved is not None:
            reports = [r for r in reports if r.resolved == resolved]
        return reports


# ---------------------------------------------------------------------------
# Rotation Scheduler
# ---------------------------------------------------------------------------

class RotationScheduler:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lifecycle = lifecycle

    def scan_due(self, now: Optional[float] = None) -> List[KeyVersion]:
        now = now or time.time()
        return [
            kv for kv in self._lifecycle._store.all_keys()
            if kv.status == KeyStatus.ACTIVE
            and self._lifecycle._policy_engine.needs_rotation(kv, now)[0]
        ]

    def scan_due_soon(self, warn_days: int = 7,
                      now: Optional[float] = None) -> List[KeyVersion]:
        now = now or time.time()
        return [
            kv for kv in self._lifecycle._store.all_keys()
            if kv.status == KeyStatus.ACTIVE
            and self._lifecycle._policy_engine.due_soon(kv, warn_days, now)
        ]

    def auto_rotate_all(self, actor: str = "scheduler",
                        now: Optional[float] = None) -> List[Tuple[KeyVersion, KeyVersion]]:
        now = now or time.time()
        rotated = []
        for kv in self.scan_due(now):
            policy = self._lifecycle.get_policy(kv.key_type, kv.tenant_id)
            if not policy.auto_rotate:
                continue
            old, new = self._lifecycle.rotate_key(
                kv.key_type, actor=actor, tenant_id=kv.tenant_id,
                trigger=RotationTrigger.POLICY_AGE)
            rotated.append((old, new))
        return rotated

    def expire_grace_pass(self, actor: str = "scheduler",
                          now: Optional[float] = None,
                          reason: str = "grace period elapsed") -> List[KeyVersion]:
        return self._lifecycle.expire_grace_keys(actor=actor, now=now,
                                                 reason=reason)


# ---------------------------------------------------------------------------
# Grace Period Extender
# ---------------------------------------------------------------------------

class GracePeriodExtender:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lifecycle = lifecycle

    def extend(self, key_id: str, version: int,
               extra_days: int, actor: str,
               reason: Optional[str] = None) -> KeyVersion:
        kv = self._lifecycle.get_key(key_id, version)
        if kv.status != KeyStatus.GRACE:
            raise PolicyViolationError(
                f"Can only extend GRACE keys, got status={kv.status}")
        now = time.time()
        new_expires = (kv.expires_at or now) + extra_days * 86400.0
        kv = self._lifecycle._store.update_status(
            key_id, version, KeyStatus.GRACE, expires_at=new_expires)
        self._lifecycle._audit.record(
            AuditAction.GRACE_EXTENDED, key_id, kv.key_type,
            version, actor, reason=reason, tenant_id=kv.tenant_id,
            extra_days=extra_days, new_expires_at=new_expires)
        return kv


# ---------------------------------------------------------------------------
# Admin / Summary
# ---------------------------------------------------------------------------

class SecretRotationAdmin:
    def __init__(self, lifecycle: KeyLifecycleManager,
                 scheduler: RotationScheduler,
                 compromise: CompromiseResponseManager):
        self._lifecycle = lifecycle
        self._scheduler = scheduler
        self._compromise = compromise

    def summary(self, tenant_id: Optional[str] = None) -> dict:
        all_keys = self._lifecycle._store.all_keys()
        if tenant_id is not None:
            all_keys = [k for k in all_keys if k.tenant_id == tenant_id]
        by_status: Dict[str, int] = {}
        for kv in all_keys:
            by_status[kv.status.value] = by_status.get(kv.status.value, 0) + 1
        by_type: Dict[str, int] = {}
        for kv in all_keys:
            if kv.status == KeyStatus.ACTIVE:
                by_type[kv.key_type.value] = by_type.get(kv.key_type.value, 0) + 1
        due = self._scheduler.scan_due()
        due_soon = self._scheduler.scan_due_soon()
        open_reports = self._compromise.list_reports(resolved=False)
        return {
            "total_keys":              len(all_keys),
            "by_status":               by_status,
            "active_by_type":          by_type,
            "overdue_rotation":         len(due),
            "due_soon":                len(due_soon),
            "open_compromise_reports": len(open_reports),
            "audit_entries":           self._lifecycle._audit.total,
            "audit_chain_valid":        self._lifecycle._audit.verify_chain(),
        }

    def health_check(self) -> Tuple[bool, List[str]]:
        issues = []
        due = self._scheduler.scan_due()
        if due:
            issues.append(f"{len(due)} key(s) overdue for rotation")
        open_reports = self._compromise.list_reports(resolved=False)
        if open_reports:
            issues.append(f"{len(open_reports)} unresolved compromise report(s)")
        if not self._lifecycle._audit.verify_chain():
            issues.append("audit chain integrity FAILED")
        return (len(issues) == 0), issues

    def bulk_rotate(self, key_type: KeyType, actor: str,
                    tenant_id: Optional[str] = None,
                    reason: Optional[str] = None) -> List[Tuple[KeyVersion, KeyVersion]]:
        active = self._lifecycle.list_by_type(
            key_type, tenant_id=tenant_id, status=KeyStatus.ACTIVE)
        results = []
        for kv in active:
            old, new = self._lifecycle.rotate_key(
                key_type, actor=actor, tenant_id=kv.tenant_id,
                trigger=RotationTrigger.MANUAL, reason=reason)
            results.append((old, new))
        return results

    def key_audit_trail(self, key_id: str,
                        limit: int = 50) -> List[AuditEntry]:
        return self._lifecycle._audit.query(key_id=key_id, limit=limit)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_secret_rotation_system(
        master_secret: Optional[bytes] = None,
) -> Tuple[KeyLifecycleManager,
           RotationScheduler,
           CompromiseResponseManager,
           GracePeriodExtender,
           SecretRotationAdmin]:
    audit = SecretAuditChain(master_secret or os.urandom(32))
    lifecycle = KeyLifecycleManager(master_secret=master_secret, audit=audit)
    scheduler = RotationScheduler(lifecycle)
    compromise = CompromiseResponseManager(lifecycle)
    extender = GracePeriodExtender(lifecycle)
    admin = SecretRotationAdmin(lifecycle, scheduler, compromise)
    return lifecycle, scheduler, compromise, extender, admin
