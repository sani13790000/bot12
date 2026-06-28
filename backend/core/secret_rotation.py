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
    ACTIVE    = "active"     # current key -- used for new sign/encrypt
    GRACE     = "grace"      # old key -- still valid for verify/decrypt
    REVOKED   = "revoked"    # compromised -- rejected immediately
    EXPIRED   = "expired"    # past grace period -- no longer accepted
    PENDING   = "pending"    # generated, not yet activated


class RotationTrigger(str, Enum):
    SCHEDULED   = "scheduled"   # normal rotation per policy
    COMPROMISE  = "compromise"  # emergency: suspected/confirmed breach
    MANUAL      = "manual"      # operator-initiated
    POLICY_AGE  = "policy_age"  # max_age_days exceeded
    POLICY_USE  = "policy_use"  # max_uses exceeded
    BOOTSTRAP   = "bootstrap"   # first-time key generation


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


class SecretRotationError(Exception):
    """Base exception."""

class KeyNotFoundError(SecretRotationError):
    """Requested key version does not exist."""

class KeyRevokedError(SecretRotationError):
    """Key has been revoked -- reject operation."""

class KeyExpiredError(SecretRotationError):
    """Key is past grace period -- no longer accepted."""

class MissingReasonError(SecretRotationError):
    """Reason is mandatory for this action."""

class PolicyViolationError(SecretRotationError):
    """Action violates rotation policy."""

class CompromiseResponseError(SecretRotationError):
    """Error during compromise response."""


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
            "key_type":         self.key_type.value if hasattr(self.key_type, 'value') else self.key_type,
            "version":          self.version,
            "status":           self.status.value if hasattr(self.status, 'value') else self.status,
            "created_at":       self.created_at,
            "activated_at":     self.activated_at,
            "expires_at":       self.expires_at,
            "rotated_at":       self.rotated_at,
            "revoked_at":       self.revoked_at,
            "use_count":        self.use_count,
            "tenant_id":        self.tenant_id,
            "signature":        self.signature,
            "rotation_trigger": self.rotation_trigger.value if hasattr(self.rotation_trigger, 'value') else self.rotation_trigger,
        }

    @property
    def is_usable(self) -> bool:
        return self.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)

    @property
    def is_usable_for_verify(self) -> bool:
        return self.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)


@dataclass
class AuditEntry:
    seq:        int
    action:     str
    key_id:     str
    key_type:   str
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
    report_id:   str
    key_id:      str
    key_type:    str
    version:     int
    reported_by: str
    reported_at: float
    reason:      str
    new_key_id:  Optional[str]
    resolved:    bool = False
    resolved_at: Optional[float] = None
    resolved_by: Optional[str] = None
    steps_taken: List[str] = field(default_factory=list)


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

    def record(self, action: str | AuditAction, key_id: str, key_type: str,
               version: int, actor: str, tenant_id: Optional[str] = None,
               reason: Optional[str] = None, detail: Optional[dict] = None) -> AuditEntry:
        action_val = action.value if hasattr(action, 'value') else action
        if action in REQUIRES_REASON or action_val in {a.value for a in REQUIRES_REASON}:
            if not reason or not reason.strip():
                raise MissingReasonError(f"reason required for action={action_val}")
        canonical = json.dumps({
            "action": action_val, "key_id": key_id, "key_type": key_type,
            "version": version, "actor": actor, "tenant_id": tenant_id,
            "reason": reason, "detail": detail or {},
        }, sort_keys=True)
        with self._lock:
            self._seq += 1
            seq = self._seq
            chain_hash = self._hmac(self._prev_hash + ":" + canonical)
            entry = AuditEntry(
                seq=seq, action=action_val, key_id=key_id, key_type=key_type,
                version=version, actor=actor, tenant_id=tenant_id,
                reason=reason, detail=detail or {}, ts=time.time(),
                prev_hash=self._prev_hash, chain_hash=chain_hash,
            )
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
                "action": e.action, "key_id": e.key_id, "key_type": e.key_type,
                "version": e.version, "actor": e.actor, "tenant_id": e.tenant_id,
                "reason": e.reason, "detail": e.detail,
            }, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                return False
            prev = e.chain_hash
        return True

    def detect_tampered(self) -> List[int]:
        with self._lock:
            entries = list(self._entries)
        broken = []
        prev = self._genesis()
        for e in entries:
            canonical = json.dumps({
                "action": e.action, "key_id": e.key_id, "key_type": e.key_type,
                "version": e.version, "actor": e.actor, "tenant_id": e.tenant_id,
                "reason": e.reason, "detail": e.detail,
            }, sort_keys=True)
            expected = self._hmac(prev + ":" + canonical)
            if not hmac.compare_digest(expected, e.chain_hash):
                broken.append(e.seq)
            prev = e.chain_hash
        return broken

    def query(self, key_id: Optional[str] = None, action: Optional[str] = None,
              key_type: Optional[str] = None, limit: int = 100) -> List[AuditEntry]:
        with self._lock:
            entries = list(self._entries)
        entries = list(reversed(entries))
        if key_id:
            entries = [e for e in entries if e.key_id == key_id]
        if action:
            entries = [e for e in entries if e.action == action]
        if key_type:
            entries = [e for e in entries if e.key_type == key_type]
        if limit and limit > 0:
            entries = entries[:limit]
        return entries

    def query_limit_zero(self) -> List[AuditEntry]:
        """query with limit=0 returns all entries."""
        with self._lock:
            return list(reversed(list(self._entries)))

    @property
    def total(self) -> int:
        with self._lock:
            return self._seq


class KeyMaterialGenerator:
    KEY_SIZES: Dict[str, int] = {
        KeyType.JWT_SIGNING.value:      64,
        KeyType.JWT_REFRESH.value:      64,
        KeyType.ENCRYPTION_DEK.value:   32,
        KeyType.ENCRYPTION_KEK.value:   32,
        KeyType.SIGNING_ARTIFACT.value: 64,
        KeyType.WEBHOOK_HMAC.value:     32,
        KeyType.AUDIT_CHAIN.value:      32,
        KeyType.API_SECRET.value:       32,
        KeyType.BACKUP_ENCRYPT.value:   32,
        KeyType.TENANT_ISOLATION.value: 32,
    }

    @classmethod
    def generate(cls, key_type: str) -> bytes:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        size = cls.KEY_SIZES.get(kt, 32)
        return secrets.token_bytes(size)

    @classmethod
    def key_size(cls, key_type: str) -> int:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        return cls.KEY_SIZES.get(kt, 32)


class KeySelfAuth:
    def __init__(self, master_secret: bytes | str):
        self._master = master_secret.encode() if isinstance(master_secret, str) else master_secret

    def sign(self, kv: KeyVersion) -> str:
        kt = kv.key_type.value if hasattr(kv.key_type, 'value') else kv.key_type
        canonical = json.dumps({
            "key_id":    kv.key_id,
            "key_type":  kt,
            "version":   kv.version,
            "tenant_id": kv.tenant_id,
        }, sort_keys=True)
        return hmac.new(self._master, canonical.encode(), hashlib.sha256).hexdigest()

    def verify(self, kv: KeyVersion) -> bool:
        expected = self.sign(kv)
        return hmac.compare_digest(expected, kv.signature)


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
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            for kv in self._store.values():
                kv_kt = kv.key_type.value if hasattr(kv.key_type, 'value') else kv.key_type
                if kv_kt == kt and kv.version == version:
                    if tenant_id is None or kv.tenant_id == tenant_id:
                        return kv
        raise KeyNotFoundError(f"type={kt} v={version}")

    def active_key(self, key_type: str, tenant_id: Optional[str] = None) -> KeyVersion:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            candidates = [
                kv for kv in self._store.values()
                if (kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type) == kt
                and kv.status == KeyStatus.ACTIVE
                and (tenant_id is None or kv.tenant_id == tenant_id)
            ]
        if not candidates:
            raise KeyNotFoundError(f"no active key for type={kt}")
        return max(candidates, key=lambda k: k.version)

    def usable_keys(self, key_type: str, tenant_id: Optional[str] = None) -> List[KeyVersion]:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            return [
                kv for kv in self._store.values()
                if (kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type) == kt
                and kv.status in (KeyStatus.ACTIVE, KeyStatus.GRACE)
                and (tenant_id is None or kv.tenant_id == tenant_id)
            ]

    def list_by_type(self, key_type: str) -> List[KeyVersion]:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            return [kv for kv in self._store.values()
                    if (kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type) == kt]

    def list_all(self, tenant_id: Optional[str] = None,
                 status: Optional[str] = None) -> List[KeyVersion]:
        with self._lock:
            result = list(self._store.values())
        if tenant_id:
            result = [k for k in result if k.tenant_id == tenant_id]
        if status:
            st = status.value if hasattr(status, 'value') else status
            result = [k for k in result if (k.status.value if hasattr(k.status,'value') else k.status) == st]
        return result

    def update_status(self, key_id: str, status: KeyStatus,
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

    def count_by_status(self) -> Dict[str, int]:
        with self._lock:
            counts: Dict[str, int] = {}
            for kv in self._store.values():
                st = kv.status.value if hasattr(kv.status, 'value') else kv.status
                counts[st] = counts.get(st, 0) + 1
        return counts


class RotationPolicyEngine:
    def __init__(self, policies: Optional[Dict] = None):
        if policies is not None:
            self._policies = copy.deepcopy(policies)
        else:
            self._policies = {
                kt: RotationPolicy.default_for(kt)
                for kt in KeyType
            }
        self._lock = threading.Lock()

    def get_policy(self, key_type: KeyType | str,
                   tenant_id: Optional[str] = None) -> RotationPolicy:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            tenant_key = f"{kt}:{tenant_id}" if tenant_id else None
            if tenant_key and tenant_key in self._policies:
                return self._policies[tenant_key]
            # Try both KeyType enum and string
            for key_type_obj in KeyType:
                if key_type_obj.value == kt or key_type_obj == key_type:
                    if key_type_obj in self._policies:
                        return self._policies[key_type_obj]
            if kt in self._policies:
                return self._policies[kt]
            return RotationPolicy.default_for(KeyType(kt) if kt in [k.value for k in KeyType] else key_type)

    def set_tenant_policy(self, key_type: str, tenant_id: str,
                          policy: RotationPolicy) -> None:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            self._policies[f"{kt}:{tenant_id}"] = policy

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
        self._audit = audit if audit is not None else SecretAuditChain()
        self._policy = policy_engine if policy_engine is not None else RotationPolicyEngine()
        self._signer = KeySelfAuth(self._master)
        self._generator = KeyMaterialGenerator()
        self._hooks: List[Callable] = []
        self._lock = threading.Lock()

    def generate(self, key_type: KeyType | str, actor: str = "system",
                 tenant_id: Optional[str] = None) -> KeyVersion:
        """Generate a new key in PENDING state (not yet active)."""
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        mat = KeyMaterialGenerator.generate(kt)
        existing = self._store.list_by_type(kt)
        version = max((kv.version for kv in existing), default=0) + 1
        kv = KeyVersion(
            key_id=str(uuid.uuid4()), key_type=key_type, version=version,
            status=KeyStatus.PENDING, created_at=time.time(),
            activated_at=None, expires_at=None, rotated_at=None,
            revoked_at=None, use_count=0, tenant_id=tenant_id,
            _raw=mat, rotation_trigger=RotationTrigger.BOOTSTRAP,
        )
        kv.signature = self._signer.sign(kv)
        self._store.add(kv)
        self._audit.record(AuditAction.KEY_GENERATED, kv.key_id, kt, kv.version,
                           actor, tenant_id)
        return kv

    def activate(self, key_id: str, actor: str) -> KeyVersion:
        """Move a PENDING key to ACTIVE."""
        kv = self._store.get(key_id)
        if kv.status != KeyStatus.PENDING:
            raise PolicyViolationError(f"key {key_id} not PENDING")
        self._store.update_status(key_id, KeyStatus.ACTIVE)
        kv.activated_at = time.time()
        self._audit.record(AuditAction.KEY_ACTIVATED, key_id, 
                           kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type,
                           kv.version, actor, kv.tenant_id)
        self._run_hooks("activate", kv)
        return kv

    def bootstrap(self, key_type: KeyType | str, actor: str = "system",
                  tenant_id: Optional[str] = None) -> KeyVersion:
        """Generate + immediately activate a key (bootstrap shortcut)."""
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        mat = KeyMaterialGenerator.generate(kt)
        existing = self._store.list_by_type(kt)
        existing_tenant = [k for k in existing if k.tenant_id == tenant_id]
        version = max((kv.version for kv in existing_tenant), default=0) + 1
        kv = KeyVersion(
            key_id=str(uuid.uuid4()), key_type=key_type, version=version,
            status=KeyStatus.ACTIVE, created_at=time.time(),
            activated_at=time.time(), expires_at=None, rotated_at=None,
            revoked_at=None, use_count=0, tenant_id=tenant_id,
            _raw=mat, rotation_trigger=RotationTrigger.BOOTSTRAP,
        )
        kv.signature = self._signer.sign(kv)
        self._store.add(kv)
        self._audit.record(AuditAction.KEY_GENERATED, kv.key_id, kt, kv.version,
                           actor, tenant_id)
        self._audit.record(AuditAction.KEY_ACTIVATED, kv.key_id, kt, kv.version,
                           actor, tenant_id)
        self._run_hooks("bootstrap", kv)
        return kv

    def rotate(self, key_type: KeyType | str, actor: str, reason: str,
               trigger: RotationTrigger = RotationTrigger.MANUAL,
               tenant_id: Optional[str] = None) -> Tuple[Optional[KeyVersion], KeyVersion]:
        """Zero-downtime rotation: old -> GRACE, new -> ACTIVE."""
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for rotation")
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        try:
            old = self._store.active_key(kt, tenant_id)
        except KeyNotFoundError:
            old = None
        policy = self._policy.get_policy(key_type, tenant_id)
        new_version = (old.version + 1) if old else 1
        mat = KeyMaterialGenerator.generate(kt)
        new_kv = KeyVersion(
            key_id=str(uuid.uuid4()), key_type=key_type, version=new_version,
            status=KeyStatus.ACTIVE, created_at=time.time(),
            activated_at=time.time(), expires_at=None, rotated_at=None,
            revoked_at=None, use_count=0, tenant_id=tenant_id,
            _raw=mat, rotation_trigger=trigger,
        )
        new_kv.signature = self._signer.sign(new_kv)
        self._store.add(new_kv)
        if old:
            grace_exp = time.time() + policy.grace_seconds
            self._store.update_status(old.key_id, KeyStatus.GRACE)
            old.expires_at = grace_exp
            old.rotated_at = time.time()
        self._audit.record(AuditAction.KEY_ROTATED, new_kv.key_id, kt,
                           new_kv.version, actor, tenant_id, reason=reason)
        self._run_hooks("rotate", new_kv)
        return old, new_kv

    def revoke(self, key_id: str, actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for revoke")
        kv = self._store.get(key_id)
        self._store.update_status(key_id, KeyStatus.REVOKED, revoke_reason=reason)
        kt = kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type
        self._audit.record(AuditAction.KEY_REVOKED, key_id, kt, kv.version,
                           actor, kv.tenant_id, reason=reason)
        self._run_hooks("revoke", kv)
        return kv

    def access(self, key_type: KeyType | str, actor: str,
               tenant_id: Optional[str] = None) -> KeyVersion:
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        kv = self._store.active_key(kt, tenant_id)
        if kv.status == KeyStatus.REVOKED:
            raise KeyRevokedError(kt)
        self._store.increment_use(kv.key_id)
        self._audit.record(AuditAction.KEY_ACCESSED, kv.key_id, kt, kv.version,
                           actor, tenant_id)
        return kv

    def verify_key_signature(self, kv: KeyVersion) -> bool:
        return self._signer.verify(kv)

    def expire_grace_keys(self, actor: str = "scheduler") -> List[str]:
        expired = []
        for kv in self._store.list_all(status=KeyStatus.GRACE):
            if self._policy.grace_expired(kv):
                self._store.update_status(kv.key_id, KeyStatus.EXPIRED)
                kt = kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type
                self._audit.record(AuditAction.KEY_EXPIRED, kv.key_id, kt, kv.version,
                                   actor, kv.tenant_id, reason="grace period ended")
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

    @property
    def signer(self) -> KeySelfAuth:
        return self._signer


class CompromiseResponseManager:
    RUNBOOK = COMPROMISE_RUNBOOK

    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle
        self._reports: Dict[str, CompromiseReport] = {}
        self._lock = threading.Lock()

    def report_compromise(self, key_id: str, reported_by: str,
                          reason: str) -> CompromiseReport:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for compromise report")
        kv = self._lc.store.get(key_id)
        kt = kv.key_type.value if hasattr(kv.key_type, 'value') else kv.key_type
        # Revoke the compromised key immediately
        self._lc.store.update_status(key_id, KeyStatus.REVOKED, revoke_reason=reason)
        self._lc._audit.record(
            AuditAction.COMPROMISE_ACK, key_id, kt, kv.version,
            reported_by, kv.tenant_id, reason=reason,
        )
        # Emergency rotation
        _, new_kv = self._lc.rotate(
            kv.key_type, reported_by,
            reason=f"emergency rotation after compromise: {reason}",
            trigger=RotationTrigger.COMPROMISE,
            tenant_id=kv.tenant_id,
        )
        self._lc._audit.record(
            AuditAction.EMERGENCY_ROT, new_kv.key_id, kt, new_kv.version,
            reported_by, kv.tenant_id, reason=f"emergency: {reason}",
        )
        report = CompromiseReport(
            report_id=str(uuid.uuid4()), key_id=key_id, key_type=kt,
            version=kv.version, reported_by=reported_by,
            reported_at=time.time(), reason=reason,
            new_key_id=new_kv.key_id, resolved=False,
            steps_taken=self.RUNBOOK[:5],
        )
        with self._lock:
            self._reports[report.report_id] = report
        return report

    def resolve_compromise(self, report_id: str, resolved_by: str) -> CompromiseReport:
        with self._lock:
            r = self._reports.get(report_id)
            if r is None:
                raise KeyNotFoundError(report_id)
            r.resolved = True
            r.resolved_at = time.time()
            r.resolved_by = resolved_by
            r.steps_taken = self.RUNBOOK
        return r

    def open_reports(self) -> List[CompromiseReport]:
        with self._lock:
            return [r for r in self._reports.values() if not r.resolved]

    def all_reports(self) -> List[CompromiseReport]:
        with self._lock:
            return list(self._reports.values())


class RotationScheduler:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def schedule(self, key_type: KeyType | str, at_ts: float,
                 actor: str = "scheduler",
                 tenant_id: Optional[str] = None) -> str:
        job_id = str(uuid.uuid4())
        kt = key_type.value if hasattr(key_type, 'value') else key_type
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id, "key_type": kt,
                "at_ts": at_ts, "actor": actor,
                "tenant_id": tenant_id, "done": False,
                "created_at": time.time(),
            }
        return job_id

    def run_due(self) -> List[str]:
        now = time.time()
        rotated = []
        with self._lock:
            due = [j for j in self._jobs.values()
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
                    self._jobs[job["job_id"]]["done"] = True
                rotated.append(job["job_id"])
            except Exception:
                pass
        return rotated

    def pending_jobs(self) -> List[dict]:
        with self._lock:
            return [j for j in self._jobs.values() if not j["done"]]

    def all_jobs(self) -> List[dict]:
        with self._lock:
            return list(self._jobs.values())


class GracePeriodExtender:
    def __init__(self, lifecycle: KeyLifecycleManager):
        self._lc = lifecycle

    def extend(self, key_id: str, extra_seconds: float,
               actor: str, reason: str) -> KeyVersion:
        if not reason or not reason.strip():
            raise MissingReasonError("reason required for grace extension")
        kv = self._lc.store.get(key_id)
        if kv.status != KeyStatus.GRACE:
            raise PolicyViolationError(f"key {key_id} not in GRACE status")
        old_exp = kv.expires_at or time.time()
        kv.expires_at = old_exp + extra_seconds
        kt = kv.key_type.value if hasattr(kv.key_type, 'value') else kv.key_type
        self._lc._audit.record(
            AuditAction.GRACE_EXTENDED, key_id, kt, kv.version,
            actor, kv.tenant_id, reason=reason,
        )
        return kv


class SecretRotationAdmin:
    def __init__(self, lifecycle: KeyLifecycleManager,
                 scheduler: Optional[RotationScheduler] = None,
                 compromise: Optional[CompromiseResponseManager] = None):
        self._lifecycle = lifecycle
        self._scheduler = scheduler or RotationScheduler(lifecycle)
        self._compromise = compromise or CompromiseResponseManager(lifecycle)
        self._extender = GracePeriodExtender(lifecycle)

    def bootstrap_all(self, actor: str = "system",
                      tenant_id: Optional[str] = None) -> Dict[str, KeyVersion]:
        result = {}
        for kt in KeyType:
            try:
                kv = self._lifecycle.bootstrap(kt, actor, tenant_id)
                result[kt.value] = kv
            except Exception:
                pass
        return result

    def rotate_key(self, key_type: KeyType | str, actor: str, reason: str,
                   tenant_id: Optional[str] = None) -> Tuple[Optional[KeyVersion], KeyVersion]:
        return self._lifecycle.rotate(key_type, actor, reason, tenant_id=tenant_id)

    def revoke_key(self, key_id: str, actor: str, reason: str) -> KeyVersion:
        return self._lifecycle.revoke(key_id, actor, reason)

    def report_compromise(self, key_id: str, reported_by: str,
                          reason: str) -> CompromiseReport:
        return self._compromise.report_compromise(key_id, reported_by, reason)

    def summary(self, tenant_id: Optional[str] = None) -> dict:
        all_keys = self._lifecycle.store.list_all(tenant_id=tenant_id)
        by_type: Dict[str, dict] = {}
        for kv in all_keys:
            t = kv.key_type.value if hasattr(kv.key_type,'value') else kv.key_type
            if t not in by_type:
                by_type[t] = {"active": 0, "grace": 0, "revoked": 0, "expired": 0, "pending": 0}
            st = kv.status.value if hasattr(kv.status,'value') else kv.status
            by_type[t][st] = by_type[t].get(st, 0) + 1
        return {
            "total_keys":    len(all_keys),
            "by_type":       by_type,
            "open_compromises": len(self._compromise.open_reports()),
            "audit_total":   self._lifecycle.audit.total,
            "chain_valid":   self._lifecycle.audit.verify_chain(),
        }

    def verify_audit_chain(self) -> bool:
        return self._lifecycle.audit.verify_chain()

    def get_runbook(self) -> List[str]:
        return CompromiseResponseManager.RUNBOOK

    @property
    def lifecycle(self) -> KeyLifecycleManager:
        return self._lifecycle

    @property
    def audit(self) -> SecretAuditChain:
        return self._lifecycle.audit

    @property
    def compromise(self) -> CompromiseResponseManager:
        return self._compromise

    @property
    def scheduler(self) -> RotationScheduler:
        return self._scheduler

    @property
    def extender(self) -> GracePeriodExtender:
        return self._extender


def build_secret_rotation_system(
        master_secret: bytes | str = b"master",
        audit_secret: bytes | str = b"audit-secret",
) -> Tuple[KeyLifecycleManager, RotationScheduler,
           CompromiseResponseManager, GracePeriodExtender, SecretRotationAdmin]:
    audit = SecretAuditChain(audit_secret)
    policy = RotationPolicyEngine()
    lifecycle = KeyLifecycleManager(master_secret=master_secret, audit=audit,
                                    policy_engine=policy)
    scheduler = RotationScheduler(lifecycle)
    compromise = CompromiseResponseManager(lifecycle)
    extender = GracePeriodExtender(lifecycle)
    admin = SecretRotationAdmin(lifecycle, scheduler, compromise)
    return lifecycle, scheduler, compromise, extender, admin


__all__ = [
    "KeyType", "KeyStatus", "RotationTrigger", "AuditAction",
    "REQUIRES_REASON", "_POLICY_DEFAULTS", "COMPROMISE_RUNBOOK",
    "RotationPolicy", "KeyVersion", "AuditEntry", "CompromiseReport",
    "SecretAuditChain", "KeyMaterialGenerator", "KeySelfAuth",
    "KeyStore", "RotationPolicyEngine", "KeyLifecycleManager",
    "CompromiseResponseManager", "RotationScheduler", "GracePeriodExtender",
    "SecretRotationAdmin", "build_secret_rotation_system",
    "SecretRotationError", "KeyNotFoundError", "KeyRevokedError",
    "KeyExpiredError", "MissingReasonError", "PolicyViolationError",
    "CompromiseResponseError",
]